"""Iter 22 regression tests for persistent auth/session and lightweight health endpoint.

# Modules/features covered: JWT TTL/runtime claims, exp+jti validation, logout revocation, and /api/health availability.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient


sys.path.append("/app/backend")


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
JWT_TTL_MINUTES = int(os.environ.get("JWT_TTL_MINUTES") or BACK_ENV.get("JWT_TTL_MINUTES") or "0")


def _decode_no_verify(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False, "verify_exp": False})


def _token_for_user(user_id: str, ttl_minutes: int = 20, include_jti: bool = True) -> tuple[str, str | None]:
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4()) if include_jti else None
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    if include_jti:
        payload["jti"] = jti
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256"), jti


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def env_ready():
    if not BASE_URL:
        pytest.skip("Missing EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL")
    if not MONGO_URL or not DB_NAME:
        pytest.skip("Missing MONGO_URL/DB_NAME")
    if not JWT_SECRET:
        pytest.skip("Missing JWT_SECRET")
    if JWT_TTL_MINUTES <= 0:
        pytest.skip("Missing/invalid JWT_TTL_MINUTES")


@pytest.fixture(scope="module")
def db(env_ready):
    client = MongoClient(MONGO_URL)
    try:
        yield client[DB_NAME]
    finally:
        client.close()


@pytest.fixture(scope="module")
def principal_user(db):
    user = db.users.find_one(
        {"account_status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "role": 1, "name": 1, "phone": 1},
    )
    if not user:
        pytest.skip("No active user found for auth checks")
    return user


def test_health_endpoint_available_without_auth():
    res = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("status") == "ok"


def test_runtime_jwt_ttl_is_30_days_from_server_make_token(principal_user):
    from server import make_token  # local import to validate runtime server issuance

    token = make_token(principal_user["id"])
    claims = _decode_no_verify(token)
    ttl_seconds = int(claims["exp"] - claims["iat"])
    expected_seconds = JWT_TTL_MINUTES * 60
    assert abs(ttl_seconds - expected_seconds) <= 5
    assert JWT_TTL_MINUTES == 43200


def test_auth_me_accepts_valid_signed_token(principal_user):
    token, _ = _token_for_user(principal_user["id"], ttl_minutes=20, include_jti=True)
    res = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_headers(token), timeout=20)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("id") == principal_user["id"]


def test_auth_me_rejects_expired_token(principal_user):
    token, _ = _token_for_user(principal_user["id"], ttl_minutes=-1, include_jti=True)
    res = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_headers(token), timeout=20)
    assert res.status_code == 401, res.text


def test_auth_me_rejects_token_missing_jti(principal_user):
    token, _ = _token_for_user(principal_user["id"], ttl_minutes=20, include_jti=False)
    res = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_headers(token), timeout=20)
    assert res.status_code == 401, res.text


def test_logout_revokes_token_and_blocks_follow_up_me(principal_user, db):
    token, jti = _token_for_user(principal_user["id"], ttl_minutes=20, include_jti=True)
    logout = requests.post(f"{BASE_URL}/api/auth/logout", headers=_auth_headers(token), timeout=20)
    assert logout.status_code == 200, logout.text
    assert logout.json().get("success") is True

    revoked = db.revoked_tokens.find_one({"jti": jti}, {"_id": 0, "jti": 1})
    assert revoked and revoked.get("jti") == jti

    me_after = requests.get(f"{BASE_URL}/api/auth/me", headers=_auth_headers(token), timeout=20)
    assert me_after.status_code == 401, me_after.text
