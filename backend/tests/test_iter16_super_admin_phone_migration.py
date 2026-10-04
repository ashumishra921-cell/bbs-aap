"""Iter 16 migration/auth regression tests.

# Modules/features covered: super-admin phone migration state integrity, retired phone OTP blocking,
# archived session rejection, and auth/health regression with MOCKED WhatsBoost provider checks.
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

OLD_RETIRED_PHONE = "9999999999"
NEW_SUPER_ADMIN_PHONE = "9312004211"


def _make_token(user_id: str, ttl_minutes: int = 10) -> str:
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
def active_super_admin(db):
    users = list(
        db.users.find(
            {
                "phone": NEW_SUPER_ADMIN_PHONE,
                "role": "super_admin",
                "$or": [{"account_status": {"$exists": False}}, {"account_status": {"$ne": "archived"}}],
            },
            {"_id": 0},
        )
    )
    assert len(users) == 1, f"Expected exactly one active super_admin with {NEW_SUPER_ADMIN_PHONE}, got {len(users)}"
    return users[0]


@pytest.fixture(scope="module")
def archived_admin_without_phone(db):
    doc = db.users.find_one(
        {
            "role": "admin",
            "account_status": "archived",
            "$or": [
                {"phone": {"$exists": False}},
                {"phone": None},
                {"phone": ""},
            ],
        },
        {"_id": 0},
    )
    assert doc is not None, "Expected archived admin record with removed phone after merge"
    return doc


def test_health_and_auth_config_regression(env_ready):
    health = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert health.status_code == 200, health.text
    assert health.json().get("status") == "ok"

    cfg = requests.get(f"{BASE_URL}/api/auth/config", timeout=20)
    assert cfg.status_code == 200, cfg.text
    body = cfg.json()
    assert body.get("otp_channel") == "whatsapp"
    assert body.get("sms_enabled") is True
    assert body.get("demo_otp") is None


def test_migration_state_single_active_superadmin_archived_target_and_no_business_links(
    db, active_super_admin, archived_admin_without_phone
):
    assert active_super_admin["id"] != archived_admin_without_phone["id"]
    assert active_super_admin["phone"] == NEW_SUPER_ADMIN_PHONE
    assert archived_admin_without_phone.get("phone") in (None, "")

    linked_counts = {
        "subscriptions": db.subscriptions.count_documents({"user_id": archived_admin_without_phone["id"]}),
        "invoices": db.invoices.count_documents({"user_id": archived_admin_without_phone["id"]}),
        "complaints": db.complaints.count_documents({"user_id": archived_admin_without_phone["id"]}),
        "payments": db.payments.count_documents({"user_id": archived_admin_without_phone["id"]}),
    }
    assert linked_counts == {"subscriptions": 0, "invoices": 0, "complaints": 0, "payments": 0}

    retired = db.retired_phones.find_one({"phone": OLD_RETIRED_PHONE}, {"_id": 0, "phone": 1})
    assert retired == {"phone": OLD_RETIRED_PHONE}

    old_challenge = db.otp_challenges.find_one({"phone": OLD_RETIRED_PHONE}, {"_id": 0})
    new_challenge = db.otp_challenges.find_one({"phone": NEW_SUPER_ADMIN_PHONE}, {"_id": 0})
    assert old_challenge is None
    assert new_challenge is None


def test_old_retired_phone_request_otp_rejected_before_whatsboost_call_and_without_sensitive_leak(api_client, monkeypatch):
    calls = {"provider": 0, "info_logs": []}

    async def _blocked_provider(*args, **kwargs):
        calls["provider"] += 1
        raise AssertionError("Provider must not be called for retired phone")

    def _capture_info(msg, *args, **kwargs):
        text = str(msg) % args if args else str(msg)
        calls["info_logs"].append(text)

    monkeypatch.setattr(app_server, "send_whatsboost_otp", _blocked_provider)
    monkeypatch.setattr(app_server.logger, "info", _capture_info)

    res = api_client.post("/api/auth/request-otp", json={"phone": OLD_RETIRED_PHONE})
    assert res.status_code == 403, res.text
    detail = (res.json() or {}).get("detail", "")

    assert calls["provider"] == 0
    assert calls["info_logs"] == []
    assert OLD_RETIRED_PHONE not in detail
    assert NEW_SUPER_ADMIN_PHONE not in detail
    assert "appkey" not in detail.lower()
    assert "authkey" not in detail.lower()
    assert not re.search(r"\b\d{6}\b", detail)


def test_old_retired_phone_verify_otp_rejected_before_local_verify_and_without_sensitive_leak(api_client, monkeypatch):
    calls = {"verify_local": 0}

    async def _blocked_local_verify(*args, **kwargs):
        calls["verify_local"] += 1
        raise AssertionError("Local OTP verify must not run for retired phone")

    monkeypatch.setattr(app_server, "verify_local_otp", _blocked_local_verify)

    res = api_client.post("/api/auth/verify-otp", json={"phone": OLD_RETIRED_PHONE, "otp": "123456"})
    assert res.status_code == 403, res.text
    detail = (res.json() or {}).get("detail", "")

    assert calls["verify_local"] == 0
    assert OLD_RETIRED_PHONE not in detail
    assert NEW_SUPER_ADMIN_PHONE not in detail
    assert "appkey" not in detail.lower()
    assert "authkey" not in detail.lower()
    assert not re.search(r"\b\d{6}\b", detail)


def test_archived_session_token_rejected_but_active_super_admin_identity_discoverable(
    env_ready, active_super_admin, archived_admin_without_phone
):
    active_token = _make_token(active_super_admin["id"])
    ok = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_header(active_token), timeout=20)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body.get("id") == active_super_admin["id"]
    assert body.get("role") == "super_admin"
    assert body.get("phone") == NEW_SUPER_ADMIN_PHONE

    archived_token = _make_token(archived_admin_without_phone["id"])
    denied = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_header(archived_token), timeout=20)
    assert denied.status_code == 401, denied.text
    detail = (denied.json() or {}).get("detail", "")
    assert "session" in detail.lower() or "user" in detail.lower()
    assert OLD_RETIRED_PHONE not in detail
    assert NEW_SUPER_ADMIN_PHONE not in detail
