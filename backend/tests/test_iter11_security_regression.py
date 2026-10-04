"""Iter 11 security regression tests.

# Modules/features covered: OTP fail-closed throttling, OTP leakage checks, JWT requirements/revocation, file auth, invoice authorization, security headers, public-vs-local CORS behavior.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient


ENV = dotenv_values("/app/backend/.env")
FRONT_ENV = dotenv_values("/app/frontend/.env")
BASE_PUBLIC = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or FRONT_ENV.get("EXPO_PUBLIC_BACKEND_URL") or "").rstrip("/")
BASE_LOCAL = (os.environ.get("BACKEND_LOCAL_URL") or "").rstrip("/")
API_PUBLIC = f"{BASE_PUBLIC}/api"
API_LOCAL = f"{BASE_LOCAL}/api" if BASE_LOCAL else ""
JWT_SECRET = (ENV.get("JWT_SECRET") or os.environ.get("JWT_SECRET") or "").strip()
MONGO_URL = (ENV.get("MONGO_URL") or os.environ.get("MONGO_URL") or "").strip()
DB_NAME = (ENV.get("DB_NAME") or os.environ.get("DB_NAME") or "").strip()
CORS_ORIGIN = ((ENV.get("CORS_ORIGINS") or "").split(",")[0] or "").strip()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_token(user_id: str, include_exp_jti: bool = True, ttl_minutes: int = 2) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now}
    if include_exp_jti:
        payload["exp"] = now + timedelta(minutes=ttl_minutes)
        payload["jti"] = str(uuid.uuid4())
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="module")
def env_ready():
    if not BASE_PUBLIC:
        pytest.skip("EXPO_PUBLIC_BACKEND_URL missing")
    if not JWT_SECRET:
        pytest.skip("JWT_SECRET missing")
    if not MONGO_URL or not DB_NAME:
        pytest.skip("MONGO_URL/DB_NAME missing")


@pytest.fixture(scope="module")
def db(env_ready):
    client = MongoClient(MONGO_URL)
    try:
        yield client[DB_NAME]
    finally:
        client.close()


@pytest.fixture(scope="module")
def role_users(db):
    users = {}
    for role in ("super_admin", "admin", "team", "subscriber"):
        users[role] = db.users.find_one({"role": role}, {"_id": 0, "id": 1, "role": 1, "phone": 1})
    return users


def test_security_headers_on_health(env_ready):
    r = requests.get(f"{API_PUBLIC}/health", timeout=15)
    assert r.status_code == 200, r.text
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_auth_config_does_not_leak_demo_otp(env_ready):
    r = requests.get(f"{API_PUBLIC}/auth/config", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("demo_otp") is None


def test_request_otp_fail_closed_blocks_former_demo_admin_phone(env_ready):
    r = requests.post(f"{API_PUBLIC}/auth/request-otp", json={"phone": "9999999999"}, timeout=20)
    assert r.status_code == 503, r.text
    body = r.json()
    assert "OTP सेवा" in body.get("detail", "")
    assert "otp" not in body
    assert "mode" not in body


def test_request_otp_rate_limit_hits_429_when_provider_unavailable(env_ready):
    phone = f"9{uuid.uuid4().int % 10**9:09d}"
    statuses = []
    for _ in range(6):
        r = requests.post(f"{API_PUBLIC}/auth/request-otp", json={"phone": phone}, timeout=20)
        statuses.append(r.status_code)
        body_text = r.text.lower()
        assert "123456" not in body_text
        assert '"otp"' not in body_text
    assert statuses[:5] == [503, 503, 503, 503, 503], statuses
    assert statuses[5] == 429, statuses


def test_legacy_jwt_missing_exp_jti_is_rejected(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for JWT requirement test")
    token = _make_token(user["id"], include_exp_jti=False)
    r = requests.get(f"{API_PUBLIC}/auth/me", headers=_auth_header(token), timeout=15)
    assert r.status_code == 401, r.text


def test_logout_revokes_valid_jwt(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for logout revocation test")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)
    r1 = requests.post(f"{API_PUBLIC}/auth/logout", headers=_auth_header(token), timeout=15)
    assert r1.status_code == 200, r1.text
    assert r1.json().get("success") is True
    r2 = requests.get(f"{API_PUBLIC}/auth/me", headers=_auth_header(token), timeout=15)
    assert r2.status_code == 401, r2.text


def test_file_endpoint_rejects_query_token_only(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for file auth test")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)
    r = requests.get(f"{API_PUBLIC}/files/non-existent/test.png?token={token}", timeout=15)
    assert r.status_code == 401, r.text


def test_team_cannot_access_other_user_invoice(env_ready, db, role_users):
    team = role_users.get("team")
    if not team:
        pytest.skip("Team user missing")
    inv = db.invoices.find_one({"user_id": {"$ne": team["id"]}}, {"_id": 0, "id": 1})
    if not inv:
        pytest.skip("No cross-user invoice found")
    team_token = _make_token(team["id"], include_exp_jti=True, ttl_minutes=2)
    r = requests.get(f"{API_PUBLIC}/invoices/{inv['id']}", headers=_auth_header(team_token), timeout=15)
    assert r.status_code == 403, r.text


def test_public_preview_cors_divergence_recorded(env_ready):
    if not CORS_ORIGIN:
        pytest.skip("CORS_ORIGINS missing")
    headers = {
        "Origin": CORS_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    r = requests.options(f"{API_PUBLIC}/auth/request-otp", headers=headers, timeout=15)
    assert r.status_code == 400, f"Expected proxy-layer 400 currently observed; got {r.status_code}"


def test_local_backend_cors_allowlist_is_strict_and_correct(env_ready):
    if not API_LOCAL:
        pytest.skip("BACKEND_LOCAL_URL missing")
    if not CORS_ORIGIN:
        pytest.skip("CORS_ORIGINS missing")
    allowed_headers = {
        "Origin": CORS_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    allowed = requests.options(f"{API_LOCAL}/auth/request-otp", headers=allowed_headers, timeout=15)
    assert allowed.status_code in (200, 204), allowed.text
    assert allowed.headers.get("access-control-allow-origin") == CORS_ORIGIN
    assert allowed.headers.get("access-control-allow-credentials") != "true"

    evil_headers = {
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    blocked = requests.options(f"{API_LOCAL}/auth/request-otp", headers=evil_headers, timeout=15)
    assert blocked.status_code == 400, blocked.text
    assert blocked.headers.get("access-control-allow-origin") != "https://evil.example"
