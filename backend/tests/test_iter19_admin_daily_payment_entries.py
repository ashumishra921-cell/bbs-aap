"""Iter 19 admin daily payment entry regression tests.

# Modules/features covered: /api/subscribers creation rules, /api/admin/payment-entries auth + cash/UPI
# activation flows, screenshot ownership checks, and mocked WhatsBoost-failure non-rollback behavior.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from pymongo import MongoClient

import sys

sys.path.append("/app/backend")
import server as app_server


FRONT_ENV = dotenv_values("/app/frontend/.env")
BACK_ENV = dotenv_values("/app/backend/.env")

BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or FRONT_ENV.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or FRONT_ENV.get("EXPO_PUBLIC_BACKEND_URL")
    or ""
).rstrip("/")

MONGO_URL = (os.environ.get("MONGO_URL") or BACK_ENV.get("MONGO_URL") or "").strip()
DB_NAME = (os.environ.get("DB_NAME") or BACK_ENV.get("DB_NAME") or "").strip()
JWT_SECRET = (os.environ.get("JWT_SECRET") or BACK_ENV.get("JWT_SECRET") or "").strip()

TAG = "TEST_ITER19"


def _uid() -> str:
    return f"{TAG}_{uuid.uuid4().hex[:10]}"


def _uuid_like(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F-]{36}", value or ""))


def _token(user_id: str, ttl_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_token(user_id)}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def env_ready():
    if not BASE_URL:
        pytest.skip("Missing EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL")
    if not MONGO_URL or not DB_NAME:
        pytest.skip("Missing MONGO_URL/DB_NAME")
    if not JWT_SECRET:
        pytest.skip("Missing JWT_SECRET")


@pytest.fixture(scope="module")
def db(env_ready):
    client = MongoClient(MONGO_URL)
    try:
        yield client[DB_NAME]
    finally:
        client.close()


@pytest.fixture(scope="module")
def api_client():
    with TestClient(app_server.app) as client:
        yield client


@pytest.fixture(scope="module")
def seeded(db):
    now = datetime.now(timezone.utc)

    plan_id = _uid()
    admin_id = _uid()
    super_admin_id = _uid()
    team_id = _uid()
    subscriber_actor_id = _uid()
    target_sub_id = _uid()
    target_sub_two_id = _uid()
    other_admin_id = _uid()

    plan = {
        "id": plan_id,
        "name": f"{TAG}_PLAN_699",
        "speed_mbps": 100,
        "data_gb": 0,
        "validity_days": 30,
        "price": 699.0,
        "description": "iter19 plan",
        "active": True,
    }

    users = [
        {"id": admin_id, "phone": "9100019011", "name": f"{TAG}_ADMIN", "role": "admin", "created_at": now},
        {"id": super_admin_id, "phone": "9100019012", "name": f"{TAG}_SUPER", "role": "super_admin", "created_at": now},
        {"id": team_id, "phone": "9100019013", "name": f"{TAG}_TEAM", "role": "team", "created_at": now},
        {"id": subscriber_actor_id, "phone": "9100019014", "name": f"{TAG}_SUB_ACTOR", "role": "subscriber", "created_at": now},
        {"id": target_sub_id, "phone": "9100019015", "name": f"{TAG}_TARGET_1", "role": "subscriber", "created_at": now},
        {"id": target_sub_two_id, "phone": "9100019016", "name": f"{TAG}_TARGET_2", "role": "subscriber", "created_at": now},
        {"id": other_admin_id, "phone": "9100019017", "name": f"{TAG}_ADMIN_2", "role": "admin", "created_at": now},
    ]

    db.plans.insert_one(plan)
    db.users.insert_many(users)

    state = {
        "plan_id": plan_id,
        "user_ids": [u["id"] for u in users],
        "admin_id": admin_id,
        "super_admin_id": super_admin_id,
        "team_id": team_id,
        "subscriber_actor_id": subscriber_actor_id,
        "target_sub_id": target_sub_id,
        "target_sub_two_id": target_sub_two_id,
        "other_admin_id": other_admin_id,
    }

    try:
        yield state
    finally:
        db.whatsapp_notifications.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.files.delete_many({"owner_id": {"$in": state["user_ids"]}})
        db.payments.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.invoices.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.subscriptions.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
        db.users.delete_many({"name": {"$regex": f"^{TAG}_"}})
        db.plans.delete_many({"id": state["plan_id"]})


def test_authorization_admin_and_super_allowed_team_subscriber_forbidden(seeded):
    payload_sub_create = {"phone": "9100019021", "name": f"{TAG}_NEW_A"}

    ok_admin = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(seeded["admin_id"]),
        json=payload_sub_create,
        timeout=25,
    )
    assert ok_admin.status_code == 200, ok_admin.text

    ok_super = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(seeded["super_admin_id"]),
        json={"phone": "9100019022", "name": f"{TAG}_NEW_B"},
        timeout=25,
    )
    assert ok_super.status_code == 200, ok_super.text

    denied_team = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(seeded["team_id"]),
        json={"phone": "9100019023", "name": f"{TAG}_NOPE_TEAM"},
        timeout=25,
    )
    assert denied_team.status_code == 403

    denied_sub = requests.post(
        f"{BASE_URL}/api/admin/payment-entries",
        headers=_headers(seeded["subscriber_actor_id"]),
        json={"subscriber_id": seeded["target_sub_id"], "plan_id": seeded["plan_id"], "payment_mode": "cash"},
        timeout=25,
    )
    assert denied_sub.status_code == 403


def test_create_subscriber_upi_initial_plan_rejected_with_explanation(seeded):
    res = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(seeded["admin_id"]),
        json={
            "phone": "9100019024",
            "name": f"{TAG}_UPI_BLOCKED",
            "plan_id": seeded["plan_id"],
            "payment_mode": "upi",
        },
        timeout=25,
    )
    assert res.status_code == 400, res.text
    assert "Daily Payment Entry" in (res.json().get("detail") or "")


def test_create_subscriber_cash_initial_plan_valid_and_audited(seeded):
    res = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(seeded["admin_id"]),
        json={
            "phone": "9100019025",
            "name": f"{TAG}_CASH_OK",
            "plan_id": seeded["plan_id"],
            "payment_mode": "cash",
        },
        timeout=30,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["role"] == "subscriber"
    assert "_id" not in body
    assert body.get("activated")

    activated = body["activated"]
    payment = activated["payment"]
    invoice = activated["invoice"]
    subscription = activated["subscription"]

    assert payment["status"] == "approved"
    assert payment.get("screenshot_path") is None
    assert invoice["status"] == "paid"
    assert invoice["payment_mode"] == "cash"
    assert subscription["status"] == "active"

    assert _uuid_like(payment["id"])
    assert _uuid_like(invoice["id"])
    assert _uuid_like(subscription["id"])
    assert payment["invoice_id"] == invoice["id"]


def test_admin_payment_entry_cash_activates_immediately_and_persists(seeded):
    create_res = requests.post(
        f"{BASE_URL}/api/admin/payment-entries",
        headers=_headers(seeded["admin_id"]),
        json={"subscriber_id": seeded["target_sub_id"], "plan_id": seeded["plan_id"], "payment_mode": "cash"},
        timeout=30,
    )
    assert create_res.status_code == 200, create_res.text
    body = create_res.json()

    assert body["payment"]["status"] == "approved"
    assert body["invoice"]["status"] == "paid"
    assert body["subscription"]["status"] == "active"
    assert body["invoice"]["payment_mode"] == "cash"

    all_payments = requests.get(
        f"{BASE_URL}/api/payments",
        headers=_headers(seeded["admin_id"]),
        timeout=25,
    )
    assert all_payments.status_code == 200, all_payments.text
    created_payment = next((p for p in all_payments.json() if p["id"] == body["payment"]["id"]), None)
    assert created_payment is not None
    assert "_id" not in created_payment

    sub_active = requests.get(
        f"{BASE_URL}/api/me/subscription",
        headers=_headers(seeded["target_sub_id"]),
        timeout=25,
    )
    assert sub_active.status_code == 200, sub_active.text
    assert sub_active.json()["plan_id"] == seeded["plan_id"]


def test_upi_entry_missing_screenshot_returns_400(seeded):
    res = requests.post(
        f"{BASE_URL}/api/admin/payment-entries",
        headers=_headers(seeded["admin_id"]),
        json={"subscriber_id": seeded["target_sub_two_id"], "plan_id": seeded["plan_id"], "payment_mode": "upi"},
        timeout=25,
    )
    assert res.status_code == 400, res.text
    assert "screenshot" in (res.json().get("detail") or "").lower()


def test_upi_entry_rejects_screenshot_owned_by_another_actor(seeded, db):
    path = f"broadband-solutions-247/uploads/{seeded['other_admin_id']}/{uuid.uuid4()}.png"
    db.files.insert_one(
        {
            "path": path,
            "owner_id": seeded["other_admin_id"],
            "content_type": "image/png",
            "size": 1234,
            "created_at": datetime.now(timezone.utc),
        }
    )

    res = requests.post(
        f"{BASE_URL}/api/admin/payment-entries",
        headers=_headers(seeded["admin_id"]),
        json={
            "subscriber_id": seeded["target_sub_two_id"],
            "plan_id": seeded["plan_id"],
            "payment_mode": "upi",
            "screenshot_path": path,
            "utr": "UTR_OWNERSHIP_FAIL",
        },
        timeout=25,
    )
    assert res.status_code == 400, res.text
    assert "screenshot" in (res.json().get("detail") or "").lower()


def test_upi_entry_with_actor_owned_screenshot_and_optional_utr_persists(seeded, db):
    path = f"broadband-solutions-247/uploads/{seeded['admin_id']}/{uuid.uuid4()}.png"
    db.files.insert_one(
        {
            "path": path,
            "owner_id": seeded["admin_id"],
            "content_type": "image/png",
            "size": 2048,
            "created_at": datetime.now(timezone.utc),
        }
    )

    res = requests.post(
        f"{BASE_URL}/api/admin/payment-entries",
        headers=_headers(seeded["admin_id"]),
        json={
            "subscriber_id": seeded["target_sub_two_id"],
            "plan_id": seeded["plan_id"],
            "payment_mode": "upi",
            "screenshot_path": path,
            "utr": "UTR_ITER19_123",
        },
        timeout=30,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["payment"]["status"] == "approved"
    assert body["payment"]["screenshot_path"] == path
    assert body["payment"]["utr"] == "UTR_ITER19_123"
    assert body["invoice"]["status"] == "paid"
    assert body["invoice"]["payment_mode"] == "upi"
    assert body["invoice"]["upi_id"] == "UTR_ITER19_123"
    assert body["subscription"]["status"] == "active"

    verify_payments = requests.get(
        f"{BASE_URL}/api/payments",
        headers=_headers(seeded["admin_id"]),
        timeout=25,
    )
    assert verify_payments.status_code == 200
    found = next((p for p in verify_payments.json() if p["id"] == body["payment"]["id"]), None)
    assert found is not None
    assert found["utr"] == "UTR_ITER19_123"


def test_whatsboost_provider_failure_mocked_does_not_roll_back_business_action(seeded, api_client, monkeypatch, db):
    calls = {"whatsapp": 0, "sms": 0}

    async def _mock_whatsapp_fail(*args, **kwargs):
        calls["whatsapp"] += 1
        return False

    async def _mock_sms_fail(*args, **kwargs):
        calls["sms"] += 1
        return False

    monkeypatch.setattr(app_server, "send_whatsapp_notification", _mock_whatsapp_fail)
    monkeypatch.setattr(app_server, "send_transactional_sms", _mock_sms_fail)

    path = f"broadband-solutions-247/uploads/{seeded['super_admin_id']}/{uuid.uuid4()}.png"
    db.files.insert_one(
        {
            "path": path,
            "owner_id": seeded["super_admin_id"],
            "content_type": "image/png",
            "size": 3333,
            "created_at": datetime.now(timezone.utc),
        }
    )

    res = api_client.post(
        "/api/admin/payment-entries",
        headers=_headers(seeded["super_admin_id"]),
        json={
            "subscriber_id": seeded["target_sub_id"],
            "plan_id": seeded["plan_id"],
            "payment_mode": "upi",
            "screenshot_path": path,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["payment"]["status"] == "approved"
    assert body["invoice"]["status"] == "paid"
    assert body["subscription"]["status"] == "active"
    assert calls["whatsapp"] >= 1
    assert calls["sms"] >= 1
