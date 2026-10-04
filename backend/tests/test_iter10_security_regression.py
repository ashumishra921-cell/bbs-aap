"""Iter 10 security regression tests.

# Modules/features covered: OTP fail-closed, JWT hardening/revocation, CORS, rate-limit, file auth, role invoice access.
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
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
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
    if not BASE_URL:
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


def test_health_route_reachable_and_security_headers(env_ready):
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("status") == "ok"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_auth_config_hides_demo_otp(env_ready):
    r = requests.get(f"{API}/auth/config", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "demo_otp" in data
    assert data["demo_otp"] is None


def test_demo_admin_phone_request_otp_fails_closed(env_ready):
    r = requests.post(f"{API}/auth/request-otp", json={"phone": "9999999999"}, timeout=20)
    assert r.status_code == 503, r.text
    body = r.json()
    assert "OTP सेवा" in body.get("detail", "")
    assert "otp" not in body
    assert "mode" not in body


def test_auth_request_rate_limit_returns_429_after_rapid_attempts(env_ready):
    phone = f"9{uuid.uuid4().int % 10**9:09d}"
    saw_429 = False
    for _ in range(7):
        r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=20)
        if r.status_code == 429:
            saw_429 = True
        text = r.text.lower()
        assert "123456" not in text
        assert '"otp"' not in text
    assert saw_429 is True


def test_auth_verify_rate_limit_returns_429_and_no_sensitive_otp(env_ready):
    phone = f"8{uuid.uuid4().int % 10**9:09d}"
    saw_429 = False
    for _ in range(10):
        r = requests.post(
            f"{API}/auth/verify-otp",
            json={"phone": phone, "otp": "000000"},
            timeout=20,
        )
        if r.status_code == 429:
            saw_429 = True
        text = r.text.lower()
        assert "123456" not in text
        assert '"otp"' not in text
    assert saw_429 is True


def test_legacy_jwt_without_exp_jti_rejected(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for JWT test")
    token = _make_token(user["id"], include_exp_jti=False)
    r = requests.get(f"{API}/auth/me", headers=_auth_header(token), timeout=15)
    assert r.status_code == 401, r.text


def test_valid_short_jwt_works(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for JWT test")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)
    r = requests.get(f"{API}/auth/me", headers=_auth_header(token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == user["id"]


def test_logout_revokes_token(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for JWT test")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)

    r1 = requests.post(f"{API}/auth/logout", headers=_auth_header(token), timeout=15)
    assert r1.status_code == 200, r1.text
    assert r1.json().get("success") is True

    r2 = requests.get(f"{API}/auth/me", headers=_auth_header(token), timeout=15)
    assert r2.status_code == 401, r2.text


def test_file_query_token_only_rejected(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user found for file token test")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)
    r = requests.get(f"{API}/files/non-existent/test.png?token={token}", timeout=15)
    assert r.status_code == 401, r.text


def test_cors_preflight_blocks_evil_origin(env_ready):
    headers = {
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    r = requests.options(f"{API}/auth/request-otp", headers=headers, timeout=15)
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_cors_preflight_allows_configured_preview_origin_without_credentials(env_ready):
    if not CORS_ORIGIN:
        pytest.skip("CORS_ORIGINS missing")
    headers = {
        "Origin": CORS_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    }
    r = requests.options(f"{API}/auth/request-otp", headers=headers, timeout=15)
    assert r.status_code in (200, 204), r.text
    assert r.headers.get("access-control-allow-origin") == CORS_ORIGIN
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_team_cannot_access_other_users_invoice(env_ready, db, role_users):
    team = role_users.get("team")
    if not team:
        pytest.skip("Team user missing")
    inv = db.invoices.find_one({"user_id": {"$ne": team["id"]}}, {"_id": 0, "id": 1, "user_id": 1})
    if not inv:
        pytest.skip("No invoice found for access-control test")

    team_token = _make_token(team["id"], include_exp_jti=True, ttl_minutes=2)
    r = requests.get(f"{API}/invoices/{inv['id']}", headers=_auth_header(team_token), timeout=15)
    assert r.status_code == 403, r.text


def test_admin_super_admin_can_access_permitted_invoice(env_ready, db, role_users):
    inv = db.invoices.find_one({}, {"_id": 0, "id": 1})
    if not inv:
        pytest.skip("No invoice found for admin access test")
    for role in ("admin", "super_admin"):
        user = role_users.get(role)
        if not user:
            continue
        token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)
        r = requests.get(f"{API}/invoices/{inv['id']}", headers=_auth_header(token), timeout=15)
        assert r.status_code == 200, f"{role}: {r.status_code} {r.text}"
