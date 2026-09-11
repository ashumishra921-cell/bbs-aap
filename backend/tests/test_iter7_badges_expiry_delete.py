"""Iteration 7: badges, admin/expiring, delete account.

Uses public EXPO_PUBLIC_BACKEND_URL. Run serially (-n 0) not required, but safe:
these tests don't share cross-class state except within TestPaymentBadgesFlow.
"""
import io
import os
import struct
import zlib
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")


# ---------- helpers ----------
def _make_png() -> bytes:
    """Tiny 1x1 red PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat_raw = b"\x00\xff\x00\x00"
    idat = b"IDAT" + zlib.compress(idat_raw)
    iend = b"IEND"

    def chunk(data):
        length = struct.pack(">I", len(data) - 4)
        crc = struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)
        return length + data + crc

    return sig + chunk(ihdr) + chunk(idat) + chunk(iend)


def _login(phone: str, name: str | None = None) -> tuple[str, dict]:
    r = requests.post(f"{BASE_URL}/api/auth/request-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"phone": phone, "otp": "123456", "name": name or f"TEST_{phone[-4:]}"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]


@pytest.fixture(scope="module")
def tokens():
    sub_t, sub_u = _login("9999999996")
    team_t, team_u = _login("9999999997")
    adm_t, adm_u = _login("9999999998")
    sup_t, sup_u = _login("9999999999")
    exp_t, exp_u = _login("7222222222")
    return {
        "sub": (sub_t, sub_u), "team": (team_t, team_u),
        "admin": (adm_t, adm_u), "super": (sup_t, sup_u),
        "exp": (exp_t, exp_u),
    }


def _hdr(tok): return {"Authorization": f"Bearer {tok}"}


# ---------------- Badges ----------------
class TestBadges:
    def test_team_new_tickets_int(self, tokens):
        r = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["team"][0]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "new_tickets" in d and isinstance(d["new_tickets"], int)

    def test_admin_shape(self, tokens):
        r = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["admin"][0]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("pending_payments", "open_tickets", "expiring_soon"):
            assert k in d and isinstance(d[k], int), f"missing/typewrong {k}: {d}"

    def test_super_shape(self, tokens):
        r = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["super"][0]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("pending_payments", "open_tickets", "expiring_soon"):
            assert k in d

    def test_subscriber_expiring_test_true(self, tokens):
        r = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["exp"][0]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("expiring_soon") is True, d
        assert isinstance(d.get("days_left"), int) and d["days_left"] <= 3

    def test_subscriber_regular_not_expiring(self, tokens):
        r = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["sub"][0]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("expiring_soon") is False, d


# ---------------- Admin expiring list ----------------
class TestAdminExpiring:
    def test_admin_3days_contains_expiry_user(self, tokens):
        r = requests.get(f"{BASE_URL}/api/admin/expiring?days=3", headers=_hdr(tokens["admin"][0]), timeout=15)
        assert r.status_code == 200
        items = r.json()
        phones = [i["phone"] for i in items]
        assert "7222222222" in phones, f"7222222222 not in expiring list: {phones}"
        target = next(i for i in items if i["phone"] == "7222222222")
        assert target["plan_name"]
        assert isinstance(target["days_left"], int) and target["days_left"] <= 3
        assert target["expired"] is False

    def test_super_3days_ok(self, tokens):
        r = requests.get(f"{BASE_URL}/api/admin/expiring?days=3", headers=_hdr(tokens["super"][0]), timeout=15)
        assert r.status_code == 200
        assert any(i["phone"] == "7222222222" for i in r.json())

    def test_team_forbidden(self, tokens):
        r = requests.get(f"{BASE_URL}/api/admin/expiring?days=3", headers=_hdr(tokens["team"][0]), timeout=15)
        assert r.status_code == 403

    def test_subscriber_forbidden(self, tokens):
        r = requests.get(f"{BASE_URL}/api/admin/expiring?days=3", headers=_hdr(tokens["sub"][0]), timeout=15)
        assert r.status_code == 403

    def test_days_40_returns_more(self, tokens):
        a = requests.get(f"{BASE_URL}/api/admin/expiring?days=3", headers=_hdr(tokens["admin"][0]), timeout=15).json()
        b = requests.get(f"{BASE_URL}/api/admin/expiring?days=40", headers=_hdr(tokens["admin"][0]), timeout=15).json()
        assert len(b) >= len(a)


# ---------------- Delete account ----------------
class TestDeleteAccount:
    def test_super_admin_cannot_delete_self(self, tokens):
        r = requests.delete(f"{BASE_URL}/api/auth/me", headers=_hdr(tokens["super"][0]), timeout=15)
        assert r.status_code == 403

    def test_new_subscriber_delete_flow(self, tokens):
        # unique phone (6-9 prefix, 10 digits)
        phone = "7" + str(uuid.uuid4().int)[:9]
        tok, user = _login(phone, name="TEST_DeleteMe")
        assert user["role"] == "subscriber"
        uid = user["id"]

        # DELETE returns 200
        r = requests.delete(f"{BASE_URL}/api/auth/me", headers=_hdr(tok), timeout=15)
        assert r.status_code == 200, r.text

        # /auth/me returns 401
        r2 = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(tok), timeout=15)
        assert r2.status_code == 401

        # Not in subscribers list
        subs = requests.get(f"{BASE_URL}/api/subscribers", headers=_hdr(tokens["super"][0]), timeout=15).json()
        assert not any(s["id"] == uid for s in subs)


# ---------------- Payment badge increments/decrements ----------------
class TestPaymentBadgesFlow:
    payment_id: str | None = None
    tmp_sub_phone: str | None = None
    tmp_sub_token: str | None = None

    def test_setup_fresh_subscriber_and_create_pending_payment(self, tokens):
        # Fresh phone so we don't collide with existing pending payments on demo user
        phone = "7" + str(uuid.uuid4().int)[:9]
        tok, user = _login(phone, name="TEST_PayBadge")
        TestPaymentBadgesFlow.tmp_sub_phone = phone
        TestPaymentBadgesFlow.tmp_sub_token = tok

        # Get baseline admin badge
        before = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["admin"][0]), timeout=15).json()
        base_pending = before["pending_payments"]

        # Upload screenshot
        png = _make_png()
        files = {"file": ("test.png", io.BytesIO(png), "image/png")}
        r = requests.post(f"{BASE_URL}/api/payments/upload-screenshot", headers=_hdr(tok), files=files, timeout=30)
        assert r.status_code == 200, r.text
        path = r.json()["path"]

        # Get first plan
        plans = requests.get(f"{BASE_URL}/api/plans", timeout=15).json()
        plan_id = plans[0]["id"]

        # Create pending payment
        r = requests.post(f"{BASE_URL}/api/payments", headers=_hdr(tok),
                          json={"plan_id": plan_id, "screenshot_path": path, "utr": "TEST_BADGE_UTR"}, timeout=15)
        assert r.status_code == 200, r.text
        TestPaymentBadgesFlow.payment_id = r.json()["id"]

        # Admin badge should have incremented by at least 1
        after = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["admin"][0]), timeout=15).json()
        assert after["pending_payments"] >= base_pending + 1, (before, after)

    def test_reject_decrements(self, tokens):
        assert TestPaymentBadgesFlow.payment_id, "no payment id from setup"
        before = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["super"][0]), timeout=15).json()
        r = requests.post(f"{BASE_URL}/api/payments/{TestPaymentBadgesFlow.payment_id}/reject",
                          headers=_hdr(tokens["super"][0]), json={"reason": "TEST cleanup"}, timeout=15)
        assert r.status_code == 200, r.text
        after = requests.get(f"{BASE_URL}/api/badges", headers=_hdr(tokens["super"][0]), timeout=15).json()
        assert after["pending_payments"] == before["pending_payments"] - 1, (before, after)

    def test_cleanup_delete_tmp_subscriber(self, tokens):
        # Delete the tmp subscriber via own account
        if TestPaymentBadgesFlow.tmp_sub_token:
            r = requests.delete(f"{BASE_URL}/api/auth/me", headers=_hdr(TestPaymentBadgesFlow.tmp_sub_token), timeout=15)
            # 200 expected; if already gone, 401 is acceptable
            assert r.status_code in (200, 401)
