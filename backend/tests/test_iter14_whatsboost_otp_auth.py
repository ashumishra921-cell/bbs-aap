"""Iter 14 regression tests.

# Modules/features covered: WhatsBoost-only OTP request/verify, throttling,
# provider error handling with cleanup, no OTP leakage, and subscriber WhatsApp preference defaults.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from pymongo import MongoClient
import httpx

import sys

sys.path.append("/app/backend")
import server as app_server


FRONT_ENV = dotenv_values("/app/frontend/.env")
BACK_ENV = dotenv_values("/app/backend/.env")

JWT_SECRET = (os.environ.get("JWT_SECRET") or BACK_ENV.get("JWT_SECRET") or "").strip()
MONGO_URL = (os.environ.get("MONGO_URL") or BACK_ENV.get("MONGO_URL") or "").strip()
DB_NAME = (os.environ.get("DB_NAME") or BACK_ENV.get("DB_NAME") or "").strip()
BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or FRONT_ENV.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or FRONT_ENV.get("EXPO_PUBLIC_BACKEND_URL")
    or ""
).rstrip("/")


def _rand_phone() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


def _make_token(user_id: str, ttl_minutes: int = 5) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def env_ready():
    if not BASE_URL:
        pytest.skip("Missing EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL")
    if not JWT_SECRET:
        pytest.skip("Missing JWT_SECRET")
    if not MONGO_URL or not DB_NAME:
        pytest.skip("Missing MONGO_URL/DB_NAME")


@pytest.fixture(scope="module")
def db(env_ready):
    client = MongoClient(MONGO_URL)
    try:
        yield client[DB_NAME]
    finally:
        client.close()


@pytest.fixture(scope="module")
def api_client(env_ready):
    with TestClient(app_server.app) as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_buckets_and_runtime_cache(db):
    db.auth_throttles.delete_many(
        {"bucket": {"$in": ["otp_send:phone", "otp_send:ip", "otp_verify:phone", "otp_verify:ip"]}}
    )
    app_server._otp_last_sent.clear()


def test_auth_config_is_whatsapp_no_demo(api_client):
    r = api_client.get("/api/auth/config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("sms_enabled") is True
    assert body.get("otp_channel") == "whatsapp"
    assert body.get("demo_otp") is None


def test_request_otp_uses_mocked_whatsboost_multipart_and_persists_hashed_challenge(api_client, db, monkeypatch):
    phone = _rand_phone()
    captured: dict = {}

    class _Resp:
        status_code = 200

    class _MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            captured["url"] = url
            captured["data"] = data
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    r = api_client.post("/api/auth/request-otp", json={"phone": phone})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "whatsapp"
    assert body["otp"] is None
    assert body["is_new_user"] is True

    sent_form = captured.get("data")
    assert isinstance(sent_form, dict)
    assert set(sent_form.keys()) == {"appkey", "authkey", "to", "name", "message"}
    assert sent_form["to"] == f"91{phone}"
    assert re.fullmatch(r"91[6-9]\d{9}", sent_form["to"])

    challenge = db.otp_challenges.find_one({"phone": phone}, {"_id": 0})
    assert challenge is not None
    assert challenge["attempts"] == 0
    assert challenge["otp_hash"] != "123456"
    assert re.fullmatch(r"[a-f0-9]{64}", challenge["otp_hash"])
    expires_at = challenge["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)

    db.otp_challenges.delete_one({"phone": phone})


def test_request_otp_provider_4xx_deletes_challenge_and_returns_safe_error(api_client, db, monkeypatch):
    phone = _rand_phone()

    class _Resp:
        status_code = 400

    class _MockClient4xx:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient4xx)

    r = api_client.post("/api/auth/request-otp", json={"phone": phone})
    assert r.status_code == 502, r.text
    msg = r.json().get("detail", "")
    assert "OTP" in msg
    assert "appkey" not in msg.lower()
    assert "authkey" not in msg.lower()
    assert db.otp_challenges.find_one({"phone": phone}) is None


def test_request_otp_provider_timeout_deletes_challenge_and_returns_safe_error(api_client, db, monkeypatch):
    phone = _rand_phone()

    class _MockClientTimeout:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClientTimeout)

    r = api_client.post("/api/auth/request-otp", json={"phone": phone})
    assert r.status_code == 504, r.text
    assert db.otp_challenges.find_one({"phone": phone}) is None


def test_verify_otp_valid_local_challenge_succeeds_and_deletes_challenge(api_client, db):
    phone = _rand_phone()
    otp = "654321"
    now = datetime.now(timezone.utc)
    db.otp_challenges.update_one(
        {"phone": phone},
        {
            "$set": {
                "phone": phone,
                "otp_hash": app_server.otp_digest(phone, otp),
                "attempts": 0,
                "created_at": now,
                "expires_at": now + timedelta(minutes=5),
            }
        },
        upsert=True,
    )

    r = api_client.post("/api/auth/verify-otp", json={"phone": phone, "otp": otp, "name": "TEST_ITER14 Sub"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("token"), str) and len(body["token"]) > 20
    assert body["user"]["phone"] == phone
    assert db.otp_challenges.find_one({"phone": phone}) is None

    db.complaints.delete_many({"user_phone": phone})
    db.invoices.delete_many({"user_phone": phone})
    db.payments.delete_many({"user_phone": phone})
    db.subscriptions.delete_many({"user_id": body["user"]["id"]})
    db.users.delete_one({"id": body["user"]["id"]})


def test_verify_otp_wrong_code_increments_attempts_and_caps_at_five(api_client, db):
    phone = _rand_phone()
    now = datetime.now(timezone.utc)
    db.otp_challenges.update_one(
        {"phone": phone},
        {
            "$set": {
                "phone": phone,
                "otp_hash": app_server.otp_digest(phone, "111111"),
                "attempts": 0,
                "created_at": now,
                "expires_at": now + timedelta(minutes=5),
            }
        },
        upsert=True,
    )

    for expected_attempt in range(1, 5):
        r = api_client.post("/api/auth/verify-otp", json={"phone": phone, "otp": "000000"})
        assert r.status_code == 400, r.text
        challenge = db.otp_challenges.find_one({"phone": phone}, {"_id": 0})
        assert challenge is not None
        assert challenge["attempts"] == expected_attempt

    final = api_client.post("/api/auth/verify-otp", json={"phone": phone, "otp": "000000"})
    assert final.status_code == 400, final.text
    assert db.otp_challenges.find_one({"phone": phone}) is None


def test_verify_otp_expired_is_rejected_and_challenge_removed(api_client, db):
    phone = _rand_phone()
    now = datetime.now(timezone.utc)
    db.otp_challenges.update_one(
        {"phone": phone},
        {
            "$set": {
                "phone": phone,
                "otp_hash": app_server.otp_digest(phone, "222222"),
                "attempts": 0,
                "created_at": now - timedelta(minutes=8),
                "expires_at": now - timedelta(seconds=5),
            }
        },
        upsert=True,
    )

    r = api_client.post("/api/auth/verify-otp", json={"phone": phone, "otp": "222222"})
    assert r.status_code == 400, r.text
    assert db.otp_challenges.find_one({"phone": phone}) is None


def test_no_msg91_or_traccar_functions_called_by_otp_endpoints(api_client, db, monkeypatch):
    called = {"msg91_send": False, "msg91_verify": False, "traccar": False}

    async def _msg91_send(*args, **kwargs):
        called["msg91_send"] = True
        raise AssertionError("MSG91 should not be used")

    async def _msg91_verify(*args, **kwargs):
        called["msg91_verify"] = True
        raise AssertionError("MSG91 verify should not be used")

    async def _traccar(*args, **kwargs):
        called["traccar"] = True
        raise AssertionError("Traccar OTP should not be used")

    class _Resp:
        status_code = 200

    class _MockClientOK:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            return _Resp()

    monkeypatch.setattr(app_server, "msg91_send_otp", _msg91_send)
    monkeypatch.setattr(app_server, "msg91_verify_otp", _msg91_verify)
    monkeypatch.setattr(app_server, "send_traccar_otp", _traccar)
    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClientOK)

    request_phone = _rand_phone()
    req = api_client.post("/api/auth/request-otp", json={"phone": request_phone})
    assert req.status_code == 200, req.text

    verify_phone = _rand_phone()
    otp = "333333"
    now = datetime.now(timezone.utc)
    db.otp_challenges.update_one(
        {"phone": verify_phone},
        {
            "$set": {
                "phone": verify_phone,
                "otp_hash": app_server.otp_digest(verify_phone, otp),
                "attempts": 0,
                "created_at": now,
                "expires_at": now + timedelta(minutes=5),
            }
        },
        upsert=True,
    )
    ver = api_client.post("/api/auth/verify-otp", json={"phone": verify_phone, "otp": otp, "name": "TEST_ITER14 NS"})
    assert ver.status_code == 200, ver.text

    assert called == {"msg91_send": False, "msg91_verify": False, "traccar": False}

    user_id = ver.json()["user"]["id"]
    db.users.delete_one({"id": user_id})
    db.subscriptions.delete_many({"user_id": user_id})
    db.complaints.delete_many({"user_id": user_id})
    db.invoices.delete_many({"user_id": user_id})
    db.payments.delete_many({"user_id": user_id})


def test_whatsboost_enabled_rate_limits_still_apply(api_client, db, monkeypatch):
    class _Resp:
        status_code = 200

    class _MockClientOK:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClientOK)

    request_statuses = []
    for _ in range(6):
        phone = _rand_phone()
        r = api_client.post("/api/auth/request-otp", json={"phone": phone})
        request_statuses.append(r.status_code)

    assert request_statuses[:5] == [200] * 5, request_statuses
    assert request_statuses[5] == 429, request_statuses

    db.auth_throttles.delete_many(
        {"bucket": {"$in": ["otp_verify:phone", "otp_verify:ip"]}}
    )
    verify_statuses = []
    for _ in range(9):
        phone = _rand_phone()
        r = api_client.post("/api/auth/verify-otp", json={"phone": phone, "otp": "000000"})
        verify_statuses.append(r.status_code)

    assert verify_statuses[:8] == [400] * 8, verify_statuses
    assert verify_statuses[8] == 429, verify_statuses


def test_subscriber_preference_default_true_can_turn_off_non_subscriber_forbidden(api_client, db):
    subscriber = db.users.find_one({"role": "subscriber"}, {"_id": 0, "id": 1, "whatsapp_updates": 1})
    if not subscriber:
        pytest.skip("No subscriber available")

    original_exists = "whatsapp_updates" in subscriber
    original_value = bool(subscriber.get("whatsapp_updates", True))
    db.users.update_one({"id": subscriber["id"]}, {"$unset": {"whatsapp_updates": ""}})

    sub_token = _make_token(subscriber["id"])
    get_default = api_client.get("/api/me/whatsapp-preference", headers=_auth_header(sub_token))
    assert get_default.status_code == 200, get_default.text
    assert get_default.json() == {"enabled": True}

    turn_off = api_client.patch(
        "/api/me/whatsapp-preference",
        headers=_auth_header(sub_token),
        json={"enabled": False},
    )
    assert turn_off.status_code == 200, turn_off.text
    assert turn_off.json() == {"enabled": False}

    team_or_admin = db.users.find_one({"role": {"$in": ["team", "admin", "super_admin"]}}, {"_id": 0, "id": 1})
    if not team_or_admin:
        pytest.skip("No non-subscriber available")
    non_sub_token = _make_token(team_or_admin["id"])
    forbidden = api_client.patch(
        "/api/me/whatsapp-preference",
        headers=_auth_header(non_sub_token),
        json={"enabled": True},
    )
    assert forbidden.status_code == 403, forbidden.text

    if original_exists:
        db.users.update_one({"id": subscriber["id"]}, {"$set": {"whatsapp_updates": original_value}})
    else:
        db.users.update_one({"id": subscriber["id"]}, {"$unset": {"whatsapp_updates": ""}})


def test_frontend_source_says_whatsapp_otp_without_demo_disclosure_and_profile_default_on():
    login_src = open("/app/frontend/app/index.tsx", "r", encoding="utf-8").read()
    otp_src = open("/app/frontend/app/otp.tsx", "r", encoding="utf-8").read()
    profile_src = open("/app/frontend/app/(subscriber)/profile.tsx", "r", encoding="utf-8").read()

    assert "WhatsApp" in login_src
    assert "WhatsApp OTP" in otp_src
    assert "123456" not in login_src
    assert "123456" not in otp_src
    assert "useState(true)" in profile_src
