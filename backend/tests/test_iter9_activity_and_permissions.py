"""Iter 9 focused regression tests.

- Team activity should include only own/unassigned complaints.
- Create one pending UPI payment for admin/super-admin UI permission checks.
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
    data = {}
    for role, phone in {
        "super_admin": "9999999999",
        "admin": "9999999998",
        "team": "9999999997",
        "subscriber": "9999999996",
        "subscriber_ui2": "7489205073",
    }.items():
        tok, user = _login(phone)
        data[role] = {"token": tok, "user": user}
    return data


def test_team_activity_only_own_or_unassigned(roles):
    super_tok = roles["super_admin"]["token"]
    team_id = roles["team"]["user"]["id"]
    extra_team_phone = f"74{datetime.now(timezone.utc).strftime('%H%M%S%f')[:8]}"
    sub_tok = roles["subscriber"]["token"]

    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    rc1 = requests.post(
        f"{API}/complaints",
        headers=_h(sub_tok),
        json={"title": f"TEST_ITER9_TEAM_VISIBLE_{suffix}", "description": "team visible", "priority": "high"},
        timeout=30,
    )
    assert rc1.status_code == 200, rc1.text
    cid_visible = rc1.json()["id"]

    rc2 = requests.post(
        f"{API}/complaints",
        headers=_h(sub_tok),
        json={"title": f"TEST_ITER9_TEAM_HIDDEN_{suffix}", "description": "team hidden", "priority": "high"},
        timeout=30,
    )
    assert rc2.status_code == 200, rc2.text
    cid_hidden = rc2.json()["id"]

    create_team = requests.post(
        f"{API}/team",
        headers=_h(super_tok),
        json={"phone": extra_team_phone, "name": "TEST_ITER9_TEAM2", "role": "team"},
        timeout=30,
    )
    assert create_team.status_code == 200, create_team.text
    hidden_team_id = create_team.json()["id"]

    assign_visible = requests.patch(
        f"{API}/complaints/{cid_visible}",
        headers=_h(super_tok),
        json={"assigned_to": team_id},
        timeout=30,
    )
    assert assign_visible.status_code == 200, assign_visible.text

    assign_hidden = requests.patch(
        f"{API}/complaints/{cid_hidden}",
        headers=_h(super_tok),
        json={"assigned_to": hidden_team_id},
        timeout=30,
    )
    assert assign_hidden.status_code == 200, assign_hidden.text

    activity = requests.get(f"{API}/activity", headers=_h(roles["team"]["token"]), timeout=30)
    assert activity.status_code == 200, activity.text
    rows = activity.json()
    keys = {row["key"] for row in rows}

    assert f"complaint-{cid_visible}" in keys
    assert f"complaint-{cid_hidden}" not in keys
    assert all(row["kind"] == "complaint" for row in rows)


def test_create_pending_payment_for_ui_permissions(roles):
    super_tok = roles["super_admin"]["token"]

    new_phone = f"74{datetime.now(timezone.utc).strftime('%H%M%S%f')[:8]}"
    create_sub = requests.post(
        f"{API}/subscribers",
        headers=_h(super_tok),
        json={"phone": new_phone, "name": "TEST_ITER9_PENDING_UI"},
        timeout=30,
    )
    assert create_sub.status_code == 200, create_sub.text

    sub_tok, _ = _login(new_phone)

    rp = requests.get(f"{API}/plans", timeout=20)
    assert rp.status_code == 200, rp.text
    plans = rp.json()
    assert plans, "No plan available"
    plan_id = plans[0]["id"]

    files = {"file": ("iter9.png", _tiny_png_bytes(), "image/png")}
    ru = requests.post(
        f"{API}/payments/upload-screenshot",
        headers={"Authorization": f"Bearer {sub_tok}"},
        files=files,
        timeout=60,
    )
    assert ru.status_code == 200, ru.text
    path = ru.json()["path"]

    create = requests.post(
        f"{API}/payments",
        headers=_h(sub_tok),
        json={"plan_id": plan_id, "screenshot_path": path, "utr": f"ITER9{uuid.uuid4().hex[:6].upper()}"},
        timeout=30,
    )
    assert create.status_code == 200, create.text
    pid = create.json()["id"]

    listing = requests.get(f"{API}/payments", headers=_h(super_tok), timeout=30)
    assert listing.status_code == 200, listing.text
    items = listing.json()
    assert any(x["id"] == pid and x["status"] == "pending" for x in items)
