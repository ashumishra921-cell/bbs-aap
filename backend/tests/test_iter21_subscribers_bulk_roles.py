"""Iter 21 regression tests for subscriber create + bulk-import permissions.

# Modules/features covered: /api/subscribers create with ISP fields, legacy-plan compatibility,
# optional manual-expiry activation via assign-plan, and /api/subscribers/bulk role restrictions.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone

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

TAG = "TEST_ITER21"


def _token(user_id: str, ttl_minutes: int = 20) -> str:
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


def _slug() -> str:
    return uuid.uuid4().hex[:8]


def _phone(prefix: str = "8") -> str:
    tail = str(uuid.uuid4().int % 1_000_000_000).zfill(9)
    return f"{prefix}{tail}"


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
def principals(db):
    super_admin = db.users.find_one({"phone": "9312004211", "account_status": {"$ne": "archived"}}, {"_id": 0, "id": 1, "role": 1})
    if not super_admin or super_admin.get("role") != "super_admin":
        pytest.skip("Super Admin 9312004211 not available as active super_admin")

    admin = db.users.find_one({"role": "admin", "account_status": {"$ne": "archived"}}, {"_id": 0, "id": 1})
    team = db.users.find_one({"role": "team", "account_status": {"$ne": "archived"}}, {"_id": 0, "id": 1})
    subscriber = db.users.find_one({"role": "subscriber", "account_status": {"$ne": "archived"}}, {"_id": 0, "id": 1})

    if not admin or not team or not subscriber:
        pytest.skip("Missing one or more active principal users (admin/team/subscriber)")

    return {
        "super_admin": super_admin["id"],
        "admin": admin["id"],
        "team": team["id"],
        "subscriber": subscriber["id"],
    }


@pytest.fixture(scope="module")
def state(db):
    slug = _slug()
    legacy_plan_id = f"{TAG}_PLAN_{slug}"
    db.plans.insert_one(
        {
            "id": legacy_plan_id,
            "name": f"{TAG} Legacy {slug}",
            "speed_mbps": 75,
            "data_gb": 0,
            "validity_days": 30,
            "price": 499.0,
            "description": "legacy plan without active field",
            # intentionally no "active" key
        }
    )
    data = {"slug": slug, "legacy_plan_id": legacy_plan_id, "created_user_ids": []}
    try:
        yield data
    finally:
        if data["created_user_ids"]:
            db.subscriptions.delete_many({"user_id": {"$in": data["created_user_ids"]}})
            db.invoices.delete_many({"user_id": {"$in": data["created_user_ids"]}})
            db.payments.delete_many({"user_id": {"$in": data["created_user_ids"]}})
            db.users.delete_many({"id": {"$in": data["created_user_ids"]}})
        db.users.delete_many({"name": {"$regex": f"^{TAG}_"}})
        db.users.delete_many({"isp_user_id": {"$regex": f"^{TAG}_"}})
        db.plans.delete_one({"id": legacy_plan_id})


def test_admin_can_create_single_customer_with_isp_fields_and_persistence(principals, state):
    suffix = _slug()
    payload = {
        "phone": _phone("8"),
        "name": f"{TAG}_SINGLE_{suffix}",
        "isp_user_id": f"{TAG}_ISP_{suffix}",
        "isp_provider": "Anonet",
        "address": "Test Lane",
    }

    res = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(principals["admin"]),
        json=payload,
        timeout=30,
    )
    assert res.status_code == 200, res.text
    created = res.json()
    assert created["role"] == "subscriber"
    assert created["isp_user_id"] == payload["isp_user_id"]
    assert created["isp_provider"] == payload["isp_provider"]
    state["created_user_ids"].append(created["id"])

    verify = requests.get(f"{BASE_URL}/api/subscribers", headers=_headers(principals["admin"]), timeout=30)
    assert verify.status_code == 200, verify.text
    found = next((u for u in verify.json() if u.get("id") == created["id"]), None)
    assert found is not None
    assert found["isp_user_id"] == payload["isp_user_id"]
    assert found["isp_provider"] == payload["isp_provider"]


def test_team_and_subscriber_cannot_create_single_customer(principals, state):
    suffix = _slug()
    payload = {
        "phone": _phone("8"),
        "name": f"{TAG}_DENY_{suffix}",
        "isp_user_id": f"{TAG}_DENY_ISP_{suffix}",
        "isp_provider": "GTPL",
    }

    for role_key in ("team", "subscriber"):
        denied = requests.post(
            f"{BASE_URL}/api/subscribers",
            headers=_headers(principals[role_key]),
            json=payload,
            timeout=30,
        )
        assert denied.status_code == 403, f"{role_key} unexpected: {denied.status_code} {denied.text}"


def test_legacy_plan_without_active_true_is_accepted_and_manual_expiry_works(principals, state, db):
    suffix = _slug()
    create_payload = {
        "phone": _phone("8"),
        "name": f"{TAG}_LEGACY_{suffix}",
        "isp_user_id": f"{TAG}_LEGACY_ISP_{suffix}",
        "isp_provider": "Zepbyt",
    }
    create_res = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(principals["admin"]),
        json=create_payload,
        timeout=30,
    )
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()
    state["created_user_ids"].append(created["id"])

    # Ensure WhatsApp notifications stay mocked/untouched by opting this test user out before activation.
    db.users.update_one({"id": created["id"]}, {"$set": {"whatsapp_updates": False}})

    expiry_date = (date.today() + timedelta(days=7)).isoformat()
    assign_res = requests.post(
        f"{BASE_URL}/api/subscribers/{created['id']}/assign-plan",
        headers=_headers(principals["super_admin"]),
        json={
            "plan_id": state["legacy_plan_id"],
            "payment_mode": "free",
            "expiry_date": expiry_date,
        },
        timeout=35,
    )
    assert assign_res.status_code == 200, assign_res.text
    body = assign_res.json()
    assert body["subscription"]["plan_id"] == state["legacy_plan_id"]
    assert body["subscription"]["status"] == "active"
    assert body["invoice"]["payment_mode"] == "free"
    assert body["subscription"]["expires_at"].startswith(expiry_date)


def test_create_subscriber_optional_plan_path_accepts_legacy_plan_unless_active_false(principals, state):
    suffix = _slug()
    payload = {
        "phone": _phone("8"),
        "name": f"{TAG}_UPI_GUARD_{suffix}",
        "isp_user_id": f"{TAG}_UPI_ISP_{suffix}",
        "isp_provider": "Anonet",
        "plan_id": state["legacy_plan_id"],
        "payment_mode": "upi",
    }

    # Expected 400 payment-mode guard (not 404 plan not found) proves legacy plan is accepted by active!=False filter.
    res = requests.post(
        f"{BASE_URL}/api/subscribers",
        headers=_headers(principals["admin"]),
        json=payload,
        timeout=30,
    )
    assert res.status_code == 400, res.text
    detail = (res.json() or {}).get("detail", "")
    assert "Daily Payment Entry" in detail


def test_super_admin_bulk_import_mixed_rows_returns_counts_and_row_errors(principals, state):
    suffix = _slug()
    users = [
        {
            "name": f"{TAG}_BULK_OK_{suffix}",
            "phone": _phone("8"),
            "isp_user_id": f"{TAG}_BULK_ISP_OK_{suffix}",
            "isp_provider": "GTPL",
            "address": "Alpha Street",
        },
        {
            "name": f"{TAG}_BULK_DUP_{suffix}",
            "phone": "",
            "isp_user_id": f"{TAG}_BULK_ISP_DUP_{suffix}",
            "isp_provider": "GTPL",
        },
        {
            "name": f"{TAG}_BULK_BADPHONE_{suffix}",
            "phone": "12345",
            "isp_user_id": f"{TAG}_BULK_ISP_BAD_{suffix}",
            "isp_provider": "GTPL",
        },
    ]
    users[1]["phone"] = users[0]["phone"]

    res = requests.post(
        f"{BASE_URL}/api/subscribers/bulk",
        headers=_headers(principals["super_admin"]),
        json={"users": users},
        timeout=40,
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["created_count"] == 1
    assert body["error_count"] == 2
    assert len(body["created"]) == 1
    assert len(body["errors"]) == 2
    assert {err["row"] for err in body["errors"]} == {2, 3}

    created_user = body["created"][0]
    state["created_user_ids"].append(created_user["id"])


def test_bulk_import_forbidden_for_admin_team_subscriber(principals):
    payload = {
        "users": [
            {
                "name": f"{TAG}_BULK_DENIED",
                "phone": "8612345678",
                "isp_user_id": f"{TAG}_DENIED_ISP",
                "isp_provider": "Anonet",
            }
        ]
    }
    for role_key in ("admin", "team", "subscriber"):
        denied = requests.post(
            f"{BASE_URL}/api/subscribers/bulk",
            headers=_headers(principals[role_key]),
            json=payload,
            timeout=30,
        )
        assert denied.status_code == 403, f"{role_key} unexpected: {denied.status_code} {denied.text}"
