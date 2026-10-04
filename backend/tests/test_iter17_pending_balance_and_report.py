"""Iter 17 pending-balance/report regression tests.

# Modules/features covered: /api/me/pending-balance auth/logic and /api/admin/report dues regression
# with non-mutation checks and no WhatsBoost side effects for read-only flows.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient


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

IST = timezone(timedelta(hours=5, minutes=30))
TAG = "TEST_ITER17"


def _id() -> str:
    return f"{TAG}_{uuid.uuid4().hex[:10]}"


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
def seeded_data(db):
    now = datetime.now(timezone.utc)

    plan_active_id = _id()
    plan_due_latest_id = _id()
    plan_due_other_id = _id()

    user_active_id = _id()
    user_due_id = _id()
    user_no_sub_id = _id()
    user_other_due_id = _id()
    admin_id = _id()
    super_admin_id = _id()

    plans = [
        {
            "id": plan_active_id,
            "name": f"{TAG}_ACTIVE_799",
            "speed_mbps": 100,
            "data_gb": 0,
            "validity_days": 30,
            "price": 799.0,
            "description": "iter17 plan",
            "active": True,
        },
        {
            "id": plan_due_latest_id,
            "name": f"{TAG}_DUE_1299",
            "speed_mbps": 200,
            "data_gb": 0,
            "validity_days": 30,
            "price": 1299.0,
            "description": "iter17 plan",
            "active": True,
        },
        {
            "id": plan_due_other_id,
            "name": f"{TAG}_DUE_999",
            "speed_mbps": 80,
            "data_gb": 0,
            "validity_days": 30,
            "price": 999.0,
            "description": "iter17 plan",
            "active": True,
        },
    ]

    users = [
        {"id": user_active_id, "phone": "9100001701", "name": f"{TAG}_ACTIVE_USER", "role": "subscriber", "created_at": now},
        {"id": user_due_id, "phone": "9100001702", "name": f"{TAG}_DUE_USER", "role": "subscriber", "created_at": now},
        {"id": user_no_sub_id, "phone": "9100001703", "name": f"{TAG}_NO_SUB", "role": "subscriber", "created_at": now},
        {"id": user_other_due_id, "phone": "9100001704", "name": f"{TAG}_OTHER_DUE", "role": "subscriber", "created_at": now},
        {"id": admin_id, "phone": "9100001705", "name": f"{TAG}_ADMIN", "role": "admin", "created_at": now},
        {"id": super_admin_id, "phone": "9100001706", "name": f"{TAG}_SUPER", "role": "super_admin", "created_at": now},
    ]

    subs = [
        {
            "id": _id(),
            "user_id": user_active_id,
            "plan_id": plan_active_id,
            "plan_name": f"{TAG}_ACTIVE_799",
            "speed_mbps": 100,
            "data_gb": 0,
            "used_gb": 0.0,
            "started_at": now - timedelta(days=2),
            "expires_at": now + timedelta(days=28),
            "status": "active",
        },
        {
            "id": _id(),
            "user_id": user_due_id,
            "plan_id": plan_due_other_id,
            "plan_name": f"{TAG}_DUE_999",
            "speed_mbps": 80,
            "data_gb": 0,
            "used_gb": 0.0,
            "started_at": now - timedelta(days=65),
            "expires_at": now - timedelta(days=35),
            "status": "expired",
        },
        {
            "id": _id(),
            "user_id": user_due_id,
            "plan_id": plan_due_latest_id,
            "plan_name": f"{TAG}_DUE_1299",
            "speed_mbps": 200,
            "data_gb": 0,
            "used_gb": 0.0,
            "started_at": now - timedelta(days=32),
            "expires_at": now - timedelta(days=2),
            "status": "expired",
        },
        {
            "id": _id(),
            "user_id": user_other_due_id,
            "plan_id": plan_due_other_id,
            "plan_name": f"{TAG}_DUE_999",
            "speed_mbps": 80,
            "data_gb": 0,
            "used_gb": 0.0,
            "started_at": now - timedelta(days=40),
            "expires_at": now - timedelta(days=4),
            "status": "expired",
        },
        {
            "id": _id(),
            "user_id": user_other_due_id,
            "plan_id": plan_due_other_id,
            "plan_name": f"{TAG}_DUE_999",
            "speed_mbps": 80,
            "data_gb": 0,
            "used_gb": 0.0,
            "started_at": now - timedelta(days=80),
            "expires_at": now - timedelta(days=45),
            "status": "expired",
        },
    ]

    db.plans.insert_many(plans)
    db.users.insert_many(users)
    db.subscriptions.insert_many(subs)

    state = {
        "ids": {
            "user_active": user_active_id,
            "user_due": user_due_id,
            "user_no_sub": user_no_sub_id,
            "user_other_due": user_other_due_id,
            "admin": admin_id,
            "super_admin": super_admin_id,
        },
        "plan_due_latest_name": f"{TAG}_DUE_1299",
        "plan_due_latest_price": 1299.0,
        "plan_due_other_price": 999.0,
        "user_ids": [user_active_id, user_due_id, user_no_sub_id, user_other_due_id, admin_id, super_admin_id],
        "plan_ids": [plan_active_id, plan_due_latest_id, plan_due_other_id],
        "month": datetime.now(IST).strftime("%Y-%m"),
    }

    try:
        yield state
    finally:
        db.whatsapp_notifications.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.subscriptions.delete_many({"user_id": {"$in": state["user_ids"]}})
        db.users.delete_many({"id": {"$in": state["user_ids"]}})
        db.plans.delete_many({"id": {"$in": state["plan_ids"]}})


def test_pending_balance_active_subscriber_returns_clear(seeded_data):
    res = requests.get(
        f"{BASE_URL}/api/me/pending-balance",
        headers=_headers(seeded_data["ids"]["user_active"]),
        timeout=20,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"amount": 0.0, "status": "clear", "plan_name": None, "expired_at": None}


def test_pending_balance_latest_expired_plan_returns_due_with_price_name_and_expiry(seeded_data):
    res = requests.get(
        f"{BASE_URL}/api/me/pending-balance",
        headers=_headers(seeded_data["ids"]["user_due"]),
        timeout=20,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "due"
    assert body["amount"] == seeded_data["plan_due_latest_price"]
    assert body["plan_name"] == seeded_data["plan_due_latest_name"]
    assert body["expired_at"]


def test_pending_balance_no_subscription_returns_clear(seeded_data):
    res = requests.get(
        f"{BASE_URL}/api/me/pending-balance",
        headers=_headers(seeded_data["ids"]["user_no_sub"]),
        timeout=20,
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"amount": 0.0, "status": "clear", "plan_name": None, "expired_at": None}


def test_pending_balance_non_subscriber_role_forbidden(seeded_data):
    res = requests.get(
        f"{BASE_URL}/api/me/pending-balance",
        headers=_headers(seeded_data["ids"]["admin"]),
        timeout=20,
    )
    assert res.status_code == 403, res.text


def test_pending_balance_isolated_per_subscriber_token_and_not_cross_user(seeded_data):
    due_res = requests.get(
        f"{BASE_URL}/api/me/pending-balance",
        headers=_headers(seeded_data["ids"]["user_due"]),
        timeout=20,
    )
    clear_res = requests.get(
        f"{BASE_URL}/api/me/pending-balance",
        headers=_headers(seeded_data["ids"]["user_no_sub"]),
        timeout=20,
    )
    assert due_res.status_code == 200 and clear_res.status_code == 200
    assert due_res.json()["status"] == "due"
    assert clear_res.json()["status"] == "clear"


def test_admin_report_dues_lists_latest_expired_without_duplicates_and_not_active_users(seeded_data, db):
    sub_count_before = db.subscriptions.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})
    inv_count_before = db.invoices.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})
    pay_count_before = db.payments.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})
    wa_count_before = db.whatsapp_notifications.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})

    res = requests.get(
        f"{BASE_URL}/api/admin/report?month={seeded_data['month']}",
        headers=_headers(seeded_data["ids"]["super_admin"]),
        timeout=25,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    dues = body["dues"]["items"]

    iter_due_rows = [d for d in dues if str(d.get("name", "")).startswith(TAG)]
    due_user_ids = [d["user_id"] for d in iter_due_rows]

    assert seeded_data["ids"]["user_due"] in due_user_ids
    assert seeded_data["ids"]["user_other_due"] in due_user_ids
    assert seeded_data["ids"]["user_active"] not in due_user_ids
    assert len(due_user_ids) == len(set(due_user_ids))

    due_map = {d["user_id"]: d for d in iter_due_rows}
    assert due_map[seeded_data["ids"]["user_due"]]["amount"] == seeded_data["plan_due_latest_price"]
    assert due_map[seeded_data["ids"]["user_other_due"]]["amount"] == seeded_data["plan_due_other_price"]

    sub_count_after = db.subscriptions.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})
    inv_count_after = db.invoices.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})
    pay_count_after = db.payments.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})
    wa_count_after = db.whatsapp_notifications.count_documents({"user_id": {"$in": seeded_data["user_ids"]}})

    assert sub_count_after == sub_count_before
    assert inv_count_after == inv_count_before
    assert pay_count_after == pay_count_before
    assert wa_count_after == wa_count_before


def test_admin_report_requires_super_admin_role(seeded_data):
    res = requests.get(
        f"{BASE_URL}/api/admin/report?month={seeded_data['month']}",
        headers=_headers(seeded_data["ids"]["admin"]),
        timeout=20,
    )
    assert res.status_code == 403, res.text
