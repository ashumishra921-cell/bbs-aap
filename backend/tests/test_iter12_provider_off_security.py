"""Iter 12 backend security follow-up tests.

# Modules/features covered: provider-off OTP fail-closed behavior, throttle enforcement,
# no OTP leakage, JWT exp+jti + revocation regression, file query token rejection, invoice role denial.
"""

import os
import time
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
API = f"{BASE_URL}/api"

JWT_SECRET = (os.environ.get("JWT_SECRET") or BACK_ENV.get("JWT_SECRET") or "").strip()
MONGO_URL = (os.environ.get("MONGO_URL") or BACK_ENV.get("MONGO_URL") or "").strip()
DB_NAME = (os.environ.get("DB_NAME") or BACK_ENV.get("DB_NAME") or "").strip()
LOG_PATH = "/var/log/supervisor/backend.out.log"


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _make_token(user_id: str, include_exp_jti: bool = True, ttl_minutes: int = 2) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now}
    if include_exp_jti:
        payload["exp"] = now + timedelta(minutes=ttl_minutes)
        payload["jti"] = str(uuid.uuid4())
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _log_size() -> int:
    try:
        return os.path.getsize(LOG_PATH)
    except OSError:
        return 0


def _log_since(offset: int) -> str:
    if offset <= 0:
        return ""
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(offset)
            return handle.read()
    except OSError:
        return ""


@pytest.fixture(scope="module")
def env_ready():
    if not BASE_URL:
        pytest.skip("Backend public URL missing (EXPO_BACKEND_URL/EXPO_PUBLIC_BACKEND_URL)")
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


@pytest.fixture(autouse=True)
def clear_auth_throttle_buckets(db):
    db.auth_throttles.delete_many({"bucket": {"$in": ["otp_send:ip", "otp_verify:ip", "otp_send:phone", "otp_verify:phone"]}})


@pytest.fixture(scope="module")
def role_users(db):
    users = {}
    for role in ("super_admin", "admin", "team", "subscriber"):
        users[role] = db.users.find_one({"role": role}, {"_id": 0, "id": 1, "role": 1})
    return users


def test_auth_config_shows_provider_off_and_no_demo_otp(env_ready):
    r = requests.get(f"{API}/auth/config", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("sms_enabled") is False
    assert body.get("demo_otp") is None


def test_verify_otp_provider_off_returns_503_and_no_provider_call(env_ready):
    phone = f"9{uuid.uuid4().int % 10**9:09d}"
    marker = _log_size()

    r = requests.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "123123"}, timeout=20)
    assert r.status_code == 503, r.text
    assert "OTP सेवा" in r.json().get("detail", "")

    time.sleep(0.8)
    chunk = _log_since(marker)
    assert "control.msg91.com/api/v5/otp/verify" not in chunk
    assert f"mobile=91{phone}" not in chunk
    assert "Traccar SMS gateway accepted request" not in chunk


def test_verify_otp_rate_limit_is_enforced_provider_off(env_ready):
    phone = f"9{uuid.uuid4().int % 10**9:09d}"
    statuses = []
    for _ in range(9):
        r = requests.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "000000"}, timeout=20)
        statuses.append(r.status_code)
        lowered = r.text.lower()
        assert "123456" not in lowered
        assert '"token"' not in lowered

    assert statuses[:8] == [503] * 8, statuses
    assert statuses[8] == 429, statuses


def test_request_otp_provider_off_then_429(env_ready):
    phone = f"9{uuid.uuid4().int % 10**9:09d}"
    statuses = []
    for _ in range(6):
        r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=20)
        statuses.append(r.status_code)
        lowered = r.text.lower()
        assert "123456" not in lowered
        assert '"otp"' not in lowered

    assert statuses[:5] == [503] * 5, statuses
    assert statuses[5] == 429, statuses


def test_legacy_jwt_without_exp_jti_rejected(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user available for JWT regression check")
    token = _make_token(user["id"], include_exp_jti=False)
    r = requests.get(f"{API}/auth/me", headers=_auth_header(token), timeout=20)
    assert r.status_code == 401, r.text


def test_logout_revokes_jwt(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user available for logout regression check")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)

    r1 = requests.post(f"{API}/auth/logout", headers=_auth_header(token), timeout=20)
    assert r1.status_code == 200, r1.text
    assert r1.json().get("success") is True

    r2 = requests.get(f"{API}/auth/me", headers=_auth_header(token), timeout=20)
    assert r2.status_code == 401, r2.text


def test_files_endpoint_rejects_query_token_only(env_ready, role_users):
    user = role_users.get("subscriber") or role_users.get("admin") or role_users.get("super_admin")
    if not user:
        pytest.skip("No user available for file-token check")
    token = _make_token(user["id"], include_exp_jti=True, ttl_minutes=2)

    r = requests.get(f"{API}/files/non-existent/probe.png?token={token}", timeout=20)
    assert r.status_code == 401, r.text


def test_team_cannot_access_other_user_invoice(env_ready, db, role_users):
    team = role_users.get("team")
    if not team:
        pytest.skip("Team user unavailable")
    inv = db.invoices.find_one({"user_id": {"$ne": team["id"]}}, {"_id": 0, "id": 1})
    if not inv:
        pytest.skip("No cross-user invoice exists")

    team_token = _make_token(team["id"], include_exp_jti=True, ttl_minutes=2)
    r = requests.get(f"{API}/invoices/{inv['id']}", headers=_auth_header(team_token), timeout=20)
    assert r.status_code == 403, r.text
