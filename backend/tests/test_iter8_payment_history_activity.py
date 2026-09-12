"""Iter 8 — Payment history, activity feed, role isolation, and plan-assignment visibility.

Focus:
- Auth for all seeded roles
- /api/payment-history auth, search, filters, pagination, role isolation, dedupe
- /api/activity role scoping + version changes
- Super admin assign-plan receipts visible to subscriber + admins
"""

import os
import struct
import uuid
import zlib
from datetime import datetime, timezone

import pytest
import requests


BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
OTP = "123456"


def _tiny_png_bytes() -> bytes:
    """Minimal valid 1x1 PNG for screenshot upload tests."""

    def chunk(t: bytes, d: bytes) -> bytes:
        crc = zlib.crc32(t + d) & 0xFFFFFFFF
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00" + bytes([120, 30, 220])
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _login(phone: str, name: str | None = None) -> tuple[str, dict]:
    r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=20)
    assert r.status_code == 200, r.text
    body = {"phone": phone, "otp": OTP}
    if name:
        body["name"] = name
    r = requests.post(f"{API}/auth/verify-otp", json=body, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    return j["token"], j["user"]


@pytest.fixture(scope="module")
def env_ok():
    if not BASE_URL:
        pytest.skip("EXPO_PUBLIC_BACKEND_URL is missing")


@pytest.fixture(scope="module")
def roles(env_ok):
    out = {}
    for role, phone in {
        "super_admin": "9999999999",
        "admin": "9999999998",
        "team": "9999999997",
        "subscriber": "9999999996",
    }.items():
        tok, user = _login(phone)
        out[role] = {"token": tok, "user": user}
    return out


@pytest.fixture(scope="module")
def test_context(roles):
    """Create isolated test subscriber + cash/free/upi receipts for payment-history assertions."""
    super_tok = roles["super_admin"]["token"]

    unique_phone = f"73{str(uuid.uuid4().int)[0:8]}"
    special_name = "TEST_[a+b](x)_ITER8"

    # Create isolated subscriber (no plan initially)
    r = requests.post(
        f"{API}/subscribers",
        headers=_h(super_tok),
        json={"phone": unique_phone, "name": special_name},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    created_user = r.json()

    # Pick one plan
    rp = requests.get(f"{API}/plans", timeout=20)
    assert rp.status_code == 200
    plans = rp.json()
    assert plans, "No plans found"
    plan = next((p for p in plans if p["name"] == "Basic 50"), plans[0])

    # Assign CASH plan (invoice)
    rc = requests.post(
        f"{API}/subscribers/{created_user['id']}/assign-plan",
        headers=_h(super_tok),
        json={"plan_id": plan["id"], "payment_mode": "cash"},
        timeout=30,
    )
    assert rc.status_code == 200, rc.text
    cash_invoice_id = rc.json()["invoice"]["id"]

    # Assign FREE plan (invoice)
    rf = requests.post(
        f"{API}/subscribers/{created_user['id']}/assign-plan",
        headers=_h(super_tok),
        json={"plan_id": plan["id"], "payment_mode": "free"},
        timeout=30,
    )
    assert rf.status_code == 200, rf.text
    free_invoice_id = rf.json()["invoice"]["id"]

    # Create and approve a UPI screenshot payment
    sub_tok, sub_user = _login(unique_phone)
    files = {"file": ("iter8.png", _tiny_png_bytes(), "image/png")}
    ru = requests.post(f"{API}/payments/upload-screenshot", headers={"Authorization": f"Bearer {sub_tok}"}, files=files, timeout=60)
    assert ru.status_code == 200, ru.text
    screenshot_path = ru.json()["path"]

    rpmt = requests.post(
        f"{API}/payments",
        headers=_h(sub_tok),
        json={"plan_id": plan["id"], "screenshot_path": screenshot_path, "utr": "TESTITER8UPI"},
        timeout=30,
    )
    assert rpmt.status_code == 200, rpmt.text
    payment_id = rpmt.json()["id"]

    ra = requests.post(f"{API}/payments/{payment_id}/approve", headers=_h(super_tok), timeout=45)
    assert ra.status_code == 200, ra.text
    upi_invoice_id = ra.json()["invoice"]["id"]

    return {
        "phone": unique_phone,
        "name": special_name,
        "user_id": sub_user["id"],
        "token": sub_tok,
        "plan": plan,
        "cash_invoice_id": cash_invoice_id,
        "free_invoice_id": free_invoice_id,
        "upi_invoice_id": upi_invoice_id,
        "approved_payment_id": payment_id,
    }


# Auth + role login coverage
def test_seeded_role_logins(roles):
    assert roles["super_admin"]["user"]["role"] == "super_admin"
    assert roles["admin"]["user"]["role"] == "admin"
    assert roles["team"]["user"]["role"] == "team"
    assert roles["subscriber"]["user"]["role"] == "subscriber"


# Payment history endpoint contract + scoping
def test_payment_history_anonymous_401(env_ok):
    r = requests.get(f"{API}/payment-history", timeout=20)
    assert r.status_code == 401


def test_payment_history_subscriber_own_records_only(test_context):
    r = requests.get(
        f"{API}/payment-history?mode=all&search={test_context['phone']}&offset=0&limit=100",
        headers=_h(test_context["token"]),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["items"]
    assert rows, "Expected subscriber history rows"
    assert all(x["user_id"] == test_context["user_id"] for x in rows)


def test_payment_history_other_subscriber_cannot_see_test_user(test_context):
    token_other, _ = _login("9999999996")
    r = requests.get(
        f"{API}/payment-history?mode=all&search={test_context['phone']}&offset=0&limit=100",
        headers=_h(token_other),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


def test_payment_history_admin_search_literal_match(roles, test_context):
    # If seeded admin role is corrupted, fall back to super_admin for endpoint-behavior checks.
    admin_tok = roles["admin"]["token"] if roles["admin"]["user"].get("role") == "admin" else roles["super_admin"]["token"]
    query = requests.utils.quote(test_context["name"])  # includes regex chars []()+
    r = requests.get(
        f"{API}/payment-history?mode=all&search={query}&offset=0&limit=100",
        headers=_h(admin_tok),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["items"]
    assert any(x["user_id"] == test_context["user_id"] for x in rows)


def test_payment_history_mode_filters_cash_upi_free(roles, test_context):
    admin_tok = roles["admin"]["token"] if roles["admin"]["user"].get("role") == "admin" else roles["super_admin"]["token"]
    expected = {
        "cash": test_context["cash_invoice_id"],
        "free": test_context["free_invoice_id"],
        "upi": test_context["upi_invoice_id"],
    }
    for mode, invoice_id in expected.items():
        r = requests.get(
            f"{API}/payment-history?mode={mode}&search={test_context['phone']}&offset=0&limit=100",
            headers=_h(admin_tok),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        rows = r.json()["items"]
        assert any(x.get("invoice_id") == invoice_id for x in rows), f"Missing {mode} invoice in filtered history"
        assert all(x["payment_mode"] == mode for x in rows)


def test_payment_history_pagination_has_more(roles):
    admin_tok = roles["admin"]["token"] if roles["admin"]["user"].get("role") == "admin" else roles["super_admin"]["token"]
    r = requests.get(f"{API}/payment-history?mode=all&offset=0&limit=1", headers=_h(admin_tok), timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert isinstance(j["has_more"], bool)
    assert len(j["items"]) <= 1


def test_payment_history_approved_screenshot_not_duplicated(roles, test_context):
    admin_tok = roles["admin"]["token"] if roles["admin"]["user"].get("role") == "admin" else roles["super_admin"]["token"]
    r = requests.get(
        f"{API}/payment-history?mode=all&search={test_context['phone']}&offset=0&limit=100",
        headers=_h(admin_tok),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["items"]
    target_invoice = test_context["upi_invoice_id"]
    matched = [x for x in rows if x.get("invoice_id") == target_invoice]
    assert len(matched) == 1


# Plan visibility via API after super admin assignment
def test_new_subscriber_subscription_visible_after_assignment(test_context):
    r = requests.get(f"{API}/me/subscription", headers=_h(test_context["token"]), timeout=30)
    assert r.status_code == 200, r.text
    sub = r.json()
    assert sub is not None
    assert sub["status"] == "active"
    assert sub["plan_name"] == test_context["plan"]["name"]


# Activity feed role-scope + version checks
def test_activity_team_has_only_complaints(roles):
    team_tok = roles["team"]["token"]
    r = requests.get(f"{API}/activity", headers=_h(team_tok), timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert all(x["kind"] == "complaint" for x in rows)


def test_activity_version_changes_on_complaint_update(roles, test_context):
    # create complaint as isolated subscriber
    rc = requests.post(
        f"{API}/complaints",
        headers=_h(test_context["token"]),
        json={"title": "TEST_ITER8_ACTIVITY", "description": f"{datetime.now(timezone.utc).isoformat()}", "priority": "high"},
        timeout=30,
    )
    assert rc.status_code == 200, rc.text
    cid = rc.json()["id"]

    # subscriber sees complaint in activity
    r1 = requests.get(f"{API}/activity", headers=_h(test_context["token"]), timeout=30)
    assert r1.status_code == 200
    before = {x["key"]: x["version"] for x in r1.json() if x["key"] == f"complaint-{cid}"}
    assert before, "Complaint key missing in subscriber activity"

    # super_admin updates status (deterministic permission)
    super_tok = roles["super_admin"]["token"]
    rup = requests.patch(f"{API}/complaints/{cid}", headers=_h(super_tok), json={"status": "resolved"}, timeout=30)
    assert rup.status_code == 200, rup.text

    r2 = requests.get(f"{API}/activity", headers=_h(test_context["token"]), timeout=30)
    assert r2.status_code == 200
    after = {x["key"]: x["version"] for x in r2.json() if x["key"] == f"complaint-{cid}"}
    assert after
    assert after[f"complaint-{cid}"] != before[f"complaint-{cid}"]
