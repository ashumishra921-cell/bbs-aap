"""Iter 15 targeted regression tests.

# Modules/features covered: WhatsBoost expiry-template scheduler eligibility,
# provider payload mapping, idempotency/dedupe, safe failure handling, and admin listing sanitization.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from pymongo import MongoClient

sys.path.append("/app/backend")
import server as app_server


BACK_ENV = dotenv_values("/app/backend/.env")

JWT_SECRET = (os.environ.get("JWT_SECRET") or BACK_ENV.get("JWT_SECRET") or "").strip()
MONGO_URL = (os.environ.get("MONGO_URL") or BACK_ENV.get("MONGO_URL") or "").strip()
DB_NAME = (os.environ.get("DB_NAME") or BACK_ENV.get("DB_NAME") or "").strip()

INDIA_TZ = timezone(timedelta(hours=5, minutes=30))


def _make_token(user_id: str, ttl_minutes: int = 30) -> str:
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


@pytest.fixture(scope="module")
def role_tokens(db):
    admin = db.users.find_one({"role": "admin"}, {"_id": 0, "id": 1})
    super_admin = db.users.find_one({"role": "super_admin"}, {"_id": 0, "id": 1})
    if not admin or not super_admin:
        pytest.skip("Seeded admin/super_admin users not found")
    return {
        "admin": _make_token(admin["id"]),
        "super_admin": _make_token(super_admin["id"]),
    }


@pytest.fixture(autouse=True)
def isolate_iter15_data(db):
    yield
    db.reminders.delete_many({"name": {"$regex": "^TEST_ITER15_"}})
    db.whatsapp_notifications.delete_many({"user_id": {"$regex": "^iter15-user-"}})
    db.subscriptions.delete_many({"id": {"$regex": "^iter15-sub-"}})
    db.plans.delete_many({"id": {"$regex": "^iter15-plan-"}})
    db.users.delete_many({"id": {"$regex": "^iter15-user-"}})


@pytest.fixture
def frozen_now(monkeypatch):
    fixed_now = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(app_server, "datetime", _FrozenDateTime)
    return fixed_now


def _create_user_plan_subscription(
    db,
    *,
    name: str,
    phone_suffix: int,
    expires_at_utc: datetime,
    plan_price: float,
    whatsapp_pref: bool | None,
) -> dict:
    uid = f"iter15-user-{uuid.uuid4()}"
    pid = f"iter15-plan-{uuid.uuid4()}"
    sid = f"iter15-sub-{uuid.uuid4()}"

    user_doc = {
        "id": uid,
        "phone": f"9{phone_suffix:09d}",
        "name": name,
        "role": "subscriber",
        "created_at": datetime.now(timezone.utc),
    }
    if whatsapp_pref is not None:
        user_doc["whatsapp_updates"] = whatsapp_pref

    plan_doc = {
        "id": pid,
        "name": "TEST_ITER15_PLAN",
        "speed_mbps": 100,
        "data_gb": 0,
        "validity_days": 30,
        "price": plan_price,
        "description": "iter15",
        "active": True,
    }

    sub_doc = {
        "id": sid,
        "user_id": uid,
        "plan_id": pid,
        "plan_name": plan_doc["name"],
        "speed_mbps": 100,
        "data_gb": 0,
        "used_gb": 0.0,
        "started_at": expires_at_utc - timedelta(days=30),
        "expires_at": expires_at_utc,
        "status": "active",
    }

    db.users.insert_one(user_doc)
    db.plans.insert_one(plan_doc)
    db.subscriptions.insert_one(sub_doc)

    return {"user": user_doc, "plan": plan_doc, "sub": sub_doc}


def _ist_to_utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=INDIA_TZ).astimezone(timezone.utc)


def test_scheduler_sends_template_with_exact_multipart_numeric_variable_mapping(
    api_client, db, role_tokens, frozen_now, monkeypatch
):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_at = _ist_to_utc(target_date.year, target_date.month, target_date.day, 12, 0)
    refs = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_Multipart",
        phone_suffix=111111111,
        expires_at_utc=expires_at,
        plan_price=1299.0,
        whatsapp_pref=True,
    )

    captured = {"calls": 0, "data": None}

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
            captured["calls"] += 1
            captured["data"] = data
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["sent"] == 1
    assert body["skipped"] == 0
    assert body["failed"] == 0
    assert captured["calls"] == 1

    payload = captured["data"]
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {
        "appkey",
        "authkey",
        "to",
        "name",
        "template_id",
        "variables[{1}]",
        "variables[{2}]",
        "variables[{3}]",
    }
    assert payload["to"] == f"91{refs['user']['phone']}"
    assert payload["variables[{1}]"] == refs["user"]["name"]
    assert payload["variables[{2}]"] == target_date.strftime("%d %b %Y")
    assert payload["variables[{3}]"] == "₹1,299"

    event_key = f"expiry_template:{refs['sub']['id']}:{refs['sub']['expires_at'].isoformat()}"
    notif = db.whatsapp_notifications.find_one({"event_key": event_key}, {"_id": 0})
    assert notif is not None
    assert notif["status"] == "submitted"
    assert notif["provider_http"] == 200


def test_scheduler_eligibility_is_exact_ist_calendar_date_plus_two_days(
    api_client, db, role_tokens, frozen_now, monkeypatch
):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    eligible_expiry = _ist_to_utc(target_date.year, target_date.month, target_date.day, 11, 0)
    ineligible_expiry = _ist_to_utc(target_date.year, target_date.month, target_date.day - 1, 12, 0)

    eligible = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_Eligible",
        phone_suffix=222222222,
        expires_at_utc=eligible_expiry,
        plan_price=799.0,
        whatsapp_pref=True,
    )
    ineligible = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_Ineligible",
        phone_suffix=333333333,
        expires_at_utc=ineligible_expiry,
        plan_price=899.0,
        whatsapp_pref=True,
    )

    captured = {"calls": 0}

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
            captured["calls"] += 1
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["checked"] == 2
    assert body["sent"] == 1
    assert captured["calls"] == 1

    eligible_after = db.subscriptions.find_one({"id": eligible["sub"]["id"]}, {"_id": 0})
    ineligible_after = db.subscriptions.find_one({"id": ineligible["sub"]["id"]}, {"_id": 0})
    assert eligible_after.get("whatsapp_expiry_template_status") == "sent"
    assert "whatsapp_expiry_template_sent_at" in eligible_after
    assert "whatsapp_expiry_template_sent_at" not in ineligible_after


def test_idempotency_existing_event_key_prevents_provider_call(api_client, db, role_tokens, frozen_now, monkeypatch):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_at = _ist_to_utc(target_date.year, target_date.month, target_date.day, 12, 30)
    refs = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_Dedupe",
        phone_suffix=444444444,
        expires_at_utc=expires_at,
        plan_price=999.0,
        whatsapp_pref=True,
    )
    event_key = f"expiry_template:{refs['sub']['id']}:{refs['sub']['expires_at'].isoformat()}"
    db.whatsapp_notifications.insert_one(
        {
            "event_key": event_key,
            "user_id": refs["user"]["id"],
            "phone_suffix": refs["user"]["phone"][-4:],
            "category": "expiry_template",
            "status": "submitted",
            "created_at": datetime.now(timezone.utc),
        }
    )

    captured = {"calls": 0}

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
            captured["calls"] += 1
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["sent"] == 0
    assert body["skipped"] == 1
    assert captured["calls"] == 0

    after = db.subscriptions.find_one({"id": refs["sub"]["id"]}, {"_id": 0})
    assert after["status"] == "active"
    assert after.get("whatsapp_expiry_template_status") == "skipped"


def test_opt_out_false_skips_provider_and_marks_skipped(api_client, db, role_tokens, frozen_now, monkeypatch):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_at = _ist_to_utc(target_date.year, target_date.month, target_date.day, 13, 0)
    refs = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_OptOut",
        phone_suffix=555555555,
        expires_at_utc=expires_at,
        plan_price=1099.0,
        whatsapp_pref=False,
    )

    class _NeverCallClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            raise AssertionError("Provider should not be called for opted-out subscriber")

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _NeverCallClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["sent"] == 0
    assert body["skipped"] == 1

    reminder = db.reminders.find_one({"subscription_id": refs["sub"]["id"]}, {"_id": 0})
    assert reminder is not None
    assert reminder["status"] == "skipped"
    assert "template configured" in reminder.get("detail", "")

    notif_count = db.whatsapp_notifications.count_documents({"user_id": refs["user"]["id"]})
    assert notif_count == 0


def test_missing_preference_defaults_enabled_and_sends(api_client, db, role_tokens, frozen_now, monkeypatch):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_at = _ist_to_utc(target_date.year, target_date.month, target_date.day, 14, 0)
    _create_user_plan_subscription(
        db,
        name="TEST_ITER15_DefaultEnabled",
        phone_suffix=666666666,
        expires_at_utc=expires_at,
        plan_price=1199.0,
        whatsapp_pref=None,
    )

    captured = {"calls": 0}

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
            captured["calls"] += 1
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    assert run.json()["sent"] == 1
    assert captured["calls"] == 1


def test_provider_non_2xx_and_timeout_are_safe_and_do_not_change_plan_status(api_client, db, role_tokens, frozen_now, monkeypatch):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_500 = _ist_to_utc(target_date.year, target_date.month, target_date.day, 15, 0)
    expires_timeout = _ist_to_utc(target_date.year, target_date.month, target_date.day, 16, 0)
    sub_500 = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_Provider500",
        phone_suffix=777777777,
        expires_at_utc=expires_500,
        plan_price=1299.5,
        whatsapp_pref=True,
    )
    sub_timeout = _create_user_plan_subscription(
        db,
        name="TEST_ITER15_ProviderTimeout",
        phone_suffix=888888888,
        expires_at_utc=expires_timeout,
        plan_price=1399.0,
        whatsapp_pref=True,
    )

    calls = {"n": 0}

    class _Resp500:
        status_code = 500

    class _MockClientMixed:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return _Resp500()
            raise httpx.TimeoutException("iter15 timeout")

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClientMixed)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["sent"] == 0
    assert body["skipped"] == 2
    assert body["failed"] == 0

    event_500 = f"expiry_template:{sub_500['sub']['id']}:{sub_500['sub']['expires_at'].isoformat()}"
    event_timeout = f"expiry_template:{sub_timeout['sub']['id']}:{sub_timeout['sub']['expires_at'].isoformat()}"
    notif_500 = db.whatsapp_notifications.find_one({"event_key": event_500}, {"_id": 0})
    notif_timeout = db.whatsapp_notifications.find_one({"event_key": event_timeout}, {"_id": 0})

    assert notif_500 is not None and notif_500["status"] == "failed" and notif_500["provider_http"] == 500
    assert notif_timeout is not None and notif_timeout["status"] == "unknown"

    sub500_after = db.subscriptions.find_one({"id": sub_500["sub"]["id"]}, {"_id": 0})
    subtimeout_after = db.subscriptions.find_one({"id": sub_timeout["sub"]["id"]}, {"_id": 0})
    assert sub500_after["status"] == "active"
    assert subtimeout_after["status"] == "active"


def test_scheduler_regression_does_not_call_legacy_generic_expiry_routes(api_client, db, role_tokens, frozen_now, monkeypatch):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_at = _ist_to_utc(target_date.year, target_date.month, target_date.day, 17, 0)
    _create_user_plan_subscription(
        db,
        name="TEST_ITER15_NoLegacyCalls",
        phone_suffix=999999991,
        expires_at_utc=expires_at,
        plan_price=1499.0,
        whatsapp_pref=True,
    )

    async def _no_legacy_call(*args, **kwargs):
        raise AssertionError("Legacy expiry sender path must not be called")

    monkeypatch.setattr(app_server, "send_expiry_sms", _no_legacy_call)
    monkeypatch.setattr(app_server, "msg91_send_expiry_sms", _no_legacy_call)
    monkeypatch.setattr(app_server, "send_whatsapp_notification", _no_legacy_call)

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
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text
    assert run.json()["sent"] == 1


def test_admin_reminder_listing_exposes_template_enabled_only_and_no_provider_secrets(
    api_client, db, role_tokens, frozen_now, monkeypatch
):
    target_date = frozen_now.astimezone(INDIA_TZ).date() + timedelta(days=2)
    expires_at = _ist_to_utc(target_date.year, target_date.month, target_date.day, 18, 0)
    _create_user_plan_subscription(
        db,
        name="TEST_ITER15_AdminList",
        phone_suffix=999999992,
        expires_at_utc=expires_at,
        plan_price=999.0,
        whatsapp_pref=True,
    )

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
            return _Resp()

    monkeypatch.setattr(app_server.httpx, "AsyncClient", _MockClient)

    run = api_client.post("/api/admin/reminders/run", headers=_auth_header(role_tokens["super_admin"]))
    assert run.status_code == 200, run.text

    listing = api_client.get("/api/admin/reminders", headers=_auth_header(role_tokens["admin"]))
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert "whatsapp_template_enabled" in body
    assert isinstance(body.get("items"), list)

    serialized = str(body).lower()
    assert "appkey" not in serialized
    assert "authkey" not in serialized
    assert "variables[{1}]" not in serialized
    assert "variables[{2}]" not in serialized
    assert "variables[{3}]" not in serialized
    assert "wb_app_" not in serialized
    assert "wb_auth_" not in serialized
