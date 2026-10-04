"""Iter 13 targeted regression tests.

# Modules/features covered: /me whatsapp preference authz + defaults,
# OTP provider-off contract, secret leakage checks, WhatsBoost idempotency,
# and notification failure non-rollback behavior (mocked provider only).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.append("/app/backend")
import server as app_server


_ASYNC_LOOP = asyncio.new_event_loop()


def _run_async(coro):
    global _ASYNC_LOOP
    if _ASYNC_LOOP.is_closed():
        _ASYNC_LOOP = asyncio.new_event_loop()
    return _ASYNC_LOOP.run_until_complete(coro)


FRONT_ENV = dotenv_values("/app/frontend/.env")
BACK_ENV = dotenv_values("/app/backend/.env")

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or FRONT_ENV.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or FRONT_ENV.get("EXPO_PUBLIC_BACKEND_URL")
    or ""
).rstrip("/")
API = f"{BASE_URL}/api"

JWT_SECRET = (os.environ.get("JWT_SECRET") or BACK_ENV.get("JWT_SECRET") or "").strip()
MONGO_URL = (os.environ.get("MONGO_URL") or BACK_ENV.get("MONGO_URL") or "").strip()
DB_NAME = (os.environ.get("DB_NAME") or BACK_ENV.get("DB_NAME") or "").strip()

WHATSBOOST_APPKEY = (os.environ.get("WHATSBOOST_APPKEY") or BACK_ENV.get("WHATSBOOST_APPKEY") or "").strip()
WHATSBOOST_AUTHKEY = (os.environ.get("WHATSBOOST_AUTHKEY") or BACK_ENV.get("WHATSBOOST_AUTHKEY") or "").strip()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_token(user_id: str, ttl_minutes: int = 5) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _contains_secret(text: str) -> bool:
    lowered = (text or "").lower()
    probes = [
        "whatsboost_appkey",
        "whatsboost_authkey",
        "wb_app_",
        "wb_auth_",
        WHATSBOOST_APPKEY.lower() if WHATSBOOST_APPKEY else "",
        WHATSBOOST_AUTHKEY.lower() if WHATSBOOST_AUTHKEY else "",
    ]
    return any(p and p in lowered for p in probes)


@pytest.fixture(scope="module")
def env_ready():
    if not BASE_URL:
        pytest.skip("Missing backend public URL")
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
def role_users(db):
    users = {
        "subscriber": db.users.find_one({"role": "subscriber"}, {"_id": 0, "id": 1, "role": 1, "phone": 1, "name": 1, "whatsapp_updates": 1}),
        "team": db.users.find_one({"role": "team"}, {"_id": 0, "id": 1, "role": 1, "phone": 1, "name": 1}),
        "admin": db.users.find_one({"role": "admin"}, {"_id": 0, "id": 1, "role": 1, "phone": 1, "name": 1}),
        "super_admin": db.users.find_one({"role": "super_admin"}, {"_id": 0, "id": 1, "role": 1, "phone": 1, "name": 1}),
    }
    if not users["subscriber"]:
        pytest.skip("No subscriber user found for preference tests")
    return users


@pytest.fixture(autouse=True)
def clear_auth_throttles(db):
    db.auth_throttles.delete_many(
        {"bucket": {"$in": ["otp_send:ip", "otp_verify:ip", "otp_send:phone", "otp_verify:phone"]}}
    )


def test_health_and_basic_api_replies_do_not_leak_whatsboost_secrets(env_ready):
    for endpoint in ("/health", "/api/health", "/api/auth/config", "/api/"):
        r = requests.get(f"{BASE_URL}{endpoint}", timeout=20)
        assert r.status_code in (200, 401), r.text
        assert not _contains_secret(r.text)


def test_me_whatsapp_preference_subscriber_can_get_and_patch_own_value(env_ready, role_users, db):
    subscriber = role_users["subscriber"]
    token = _make_token(subscriber["id"])

    before = requests.get(f"{API}/me/whatsapp-preference", headers=_auth_header(token), timeout=20)
    assert before.status_code == 200, before.text
    original = bool(before.json().get("enabled", False))

    r1 = requests.patch(
        f"{API}/me/whatsapp-preference",
        headers=_auth_header(token),
        json={"enabled": not original},
        timeout=20,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["enabled"] is (not original)

    after = requests.get(f"{API}/me/whatsapp-preference", headers=_auth_header(token), timeout=20)
    assert after.status_code == 200, after.text
    assert after.json()["enabled"] is (not original)

    restore = requests.patch(
        f"{API}/me/whatsapp-preference",
        headers=_auth_header(token),
        json={"enabled": original},
        timeout=20,
    )
    assert restore.status_code == 200, restore.text
    assert db.users.find_one({"id": subscriber["id"]}, {"_id": 0}).get("whatsapp_updates", False) is original


def test_me_whatsapp_preference_non_subscriber_forbidden(env_ready, role_users):
    principal = role_users.get("team") or role_users.get("admin") or role_users.get("super_admin")
    if not principal:
        pytest.skip("No non-subscriber user found")

    token = _make_token(principal["id"])
    g = requests.get(f"{API}/me/whatsapp-preference", headers=_auth_header(token), timeout=20)
    p = requests.patch(f"{API}/me/whatsapp-preference", headers=_auth_header(token), json={"enabled": True}, timeout=20)

    assert g.status_code == 403, g.text
    assert p.status_code == 403, p.text


def test_default_opt_out_when_field_missing_and_no_notification_record_created(env_ready, role_users, db):
    subscriber = role_users["subscriber"]
    token = _make_token(subscriber["id"])

    db.users.update_one({"id": subscriber["id"]}, {"$unset": {"whatsapp_updates": ""}})

    pref = requests.get(f"{API}/me/whatsapp-preference", headers=_auth_header(token), timeout=20)
    assert pref.status_code == 200, pref.text
    assert pref.json() == {"enabled": False}

    complaint = requests.post(
        f"{API}/complaints",
        headers=_auth_header(token),
        json={"title": f"TEST_iter13_{uuid.uuid4().hex[:8]}", "description": "preference opt-out regression", "priority": "low"},
        timeout=20,
    )
    assert complaint.status_code == 200, complaint.text
    cid = complaint.json()["id"]
    event_key = f"complaint_created:{cid}"
    assert db.whatsapp_notifications.find_one({"event_key": event_key}) is None

    db.complaints.delete_one({"id": cid})


def test_otp_flows_remain_provider_off_and_do_not_surface_whatsboost(env_ready):
    request_phone = f"9{uuid.uuid4().int % 10**9:09d}"
    verify_phone = f"9{uuid.uuid4().int % 10**9:09d}"

    request_statuses = []
    for _ in range(6):
        r = requests.post(f"{API}/auth/request-otp", json={"phone": request_phone}, timeout=20)
        request_statuses.append(r.status_code)
        assert not _contains_secret(r.text)
    assert request_statuses[:5] == [503] * 5, request_statuses
    assert request_statuses[5] == 429, request_statuses

    verify_statuses = []
    for _ in range(9):
        r = requests.post(f"{API}/auth/verify-otp", json={"phone": verify_phone, "otp": "000000"}, timeout=20)
        verify_statuses.append(r.status_code)
        assert not _contains_secret(r.text)
    assert verify_statuses[:8] == [503] * 8, verify_statuses
    assert verify_statuses[8] == 429, verify_statuses


def test_frontend_source_contains_whatsapp_toggle_and_no_whatsboost_secrets():
    profile_src = Path("/app/frontend/app/(subscriber)/profile.tsx").read_text(encoding="utf-8")
    api_src = Path("/app/frontend/src/api.ts").read_text(encoding="utf-8")

    assert "testID=\"whatsapp-updates-card\"" in profile_src
    assert "testID=\"whatsapp-updates-switch\"" in profile_src
    assert "updateWhatsappPreference" in api_src
    assert "/me/whatsapp-preference" in api_src

    for path in Path("/app/frontend").rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".json", ".env"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "wb_app_" not in text.lower()
        assert "wb_auth_" not in text.lower()
        assert (WHATSBOOST_APPKEY.lower() not in text.lower()) if WHATSBOOST_APPKEY else True
        assert (WHATSBOOST_AUTHKEY.lower() not in text.lower()) if WHATSBOOST_AUTHKEY else True


def test_notification_idempotency_by_event_key_with_mocked_provider(db, role_users, monkeypatch):
    async def _run():
        subscriber = role_users["subscriber"]
        event_key = f"iter13:idempotent:{uuid.uuid4()}"
        user_doc = await app_server.db.users.find_one({"id": subscriber["id"]}, {"_id": 0})
        assert user_doc is not None

        old_pref = bool(user_doc.get("whatsapp_updates", False))
        await app_server.db.users.update_one({"id": subscriber["id"]}, {"$set": {"whatsapp_updates": True}})
        user_doc["whatsapp_updates"] = True

        class _Resp:
            status_code = 200

        class _MockClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, data=None):
                return _Resp()

        monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

        first = await app_server.send_whatsapp_notification(user_doc, event_key, "TEST first")
        second = await app_server.send_whatsapp_notification(user_doc, event_key, "TEST second")

        assert first is True
        assert second is False
        assert db.whatsapp_notifications.count_documents({"event_key": event_key}) == 1

        await app_server.db.whatsapp_notifications.delete_one({"event_key": event_key})
        await app_server.db.users.update_one({"id": subscriber["id"]}, {"$set": {"whatsapp_updates": old_pref}})

    _run_async(_run())


def test_whatsapp_non_delivery_does_not_rollback_plan_activation(monkeypatch):
    async def _run():
        plan = await app_server.db.plans.find_one({"active": {"$ne": False}}, {"_id": 0})
        if not plan:
            pytest.skip("No active plan available")

        temp_user = {
            "id": str(uuid.uuid4()),
            "phone": f"9{uuid.uuid4().int % 10**9:09d}",
            "name": "TEST Iter13 Subscriber",
            "role": "subscriber",
            "whatsapp_updates": True,
            "created_at": datetime.now(timezone.utc),
        }
        await app_server.db.users.insert_one(temp_user)

        class _Resp:
            status_code = 500

        class _MockClientFail:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, data=None):
                return _Resp()

        monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClientFail)

        result = await app_server.activate_plan(temp_user, plan, "free")
        invoice_id = result["invoice"]["id"]
        subscription_id = result["subscription"]["id"]

        saved_invoice = await app_server.db.invoices.find_one({"id": invoice_id}, {"_id": 0})
        saved_sub = await app_server.db.subscriptions.find_one({"id": subscription_id}, {"_id": 0})
        notif = await app_server.db.whatsapp_notifications.find_one({"event_key": f"plan_activation:{invoice_id}"}, {"_id": 0})

        assert saved_invoice is not None
        assert saved_sub is not None
        assert saved_sub["status"] == "active"
        assert notif is not None
        assert notif["status"] in ("failed", "unknown")

        await app_server.db.whatsapp_notifications.delete_many({"user_id": temp_user["id"]})
        await app_server.db.invoices.delete_many({"user_id": temp_user["id"]})
        await app_server.db.subscriptions.delete_many({"user_id": temp_user["id"]})
        await app_server.db.complaints.delete_many({"user_id": temp_user["id"]})
        await app_server.db.users.delete_one({"id": temp_user["id"]})

    _run_async(_run())
