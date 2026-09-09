"""Iteration 2: MSG91 demo-fallback OTP + phone normalization tests"""
import os
import random
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


# ---------------------- /auth/config ----------------------
def test_auth_config_sms_disabled_demo_otp():
    r = requests.get(f"{API}/auth/config", timeout=10)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sms_enabled"] is False
    assert j["demo_otp"] == "123456"
    assert j["resend_cooldown_sec"] == 30


# ---------------------- /auth/request-otp with normalization ----------------------
@pytest.mark.parametrize("phone_input", [
    "9999999996",
    "+91 9999999996",
    "09999999996",
    "91-9999999996",
    "+91-9999999996",
])
def test_request_otp_accepts_various_formats(phone_input):
    r = requests.post(f"{API}/auth/request-otp", json={"phone": phone_input}, timeout=15)
    assert r.status_code == 200, f"{phone_input}: {r.text}"
    j = r.json()
    assert j["mode"] == "demo"
    assert j["otp"] == "123456"
    assert j["is_new_user"] is False


def test_request_otp_rejects_invalid_short_number():
    r = requests.post(f"{API}/auth/request-otp", json={"phone": "12345"}, timeout=10)
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    # Hindi error present
    assert "मोबाइल" in detail or "अंकों" in detail, f"unexpected detail: {detail}"


def test_request_otp_rejects_invalid_prefix():
    # Starts with 5 -> not [6-9]
    r = requests.post(f"{API}/auth/request-otp", json={"phone": "5123456789"}, timeout=10)
    assert r.status_code == 400


# ---------------------- /auth/verify-otp ----------------------
def test_verify_otp_wrong_returns_hindi_error():
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"phone": "9999999996", "otp": "000000"}, timeout=10)
    assert r.status_code == 400
    assert "गलत OTP" in r.json().get("detail", "")


def test_verify_otp_correct_with_plus91_normalizes_and_logs_in():
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"phone": "+919999999996", "otp": "123456"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "token" in j
    assert j["user"]["phone"] == "9999999996"
    assert j["user"]["name"] == "Amit Sharma"
    assert j["user"]["role"] == "subscriber"


def test_verify_otp_correct_with_spaces():
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"phone": "+91 9999999996", "otp": "123456"}, timeout=15)
    assert r.status_code == 200
    assert r.json()["user"]["phone"] == "9999999996"


def test_new_user_signup_random_number_and_name():
    # random 10-digit starting 6-9 that we haven't seen
    while True:
        p = f"{random.choice('6789')}{random.randint(10**8, 10**9 - 1)}"
        # ensure not one of demo seeds
        if p not in ("9999999999", "9999999998", "9999999997", "9999999996"):
            break
    r1 = requests.post(f"{API}/auth/request-otp", json={"phone": p}, timeout=10)
    assert r1.status_code == 200
    assert r1.json()["is_new_user"] is True
    r2 = requests.post(f"{API}/auth/verify-otp",
                       json={"phone": p, "otp": "123456", "name": "TEST_NewUser"}, timeout=15)
    assert r2.status_code == 200, r2.text
    j = r2.json()
    assert j["user"]["phone"] == p
    assert j["user"]["name"] == "TEST_NewUser"
    assert j["user"]["role"] == "subscriber"


# ---------------------- Regression: role routing ----------------------
@pytest.mark.parametrize("phone,expected_role,expected_name", [
    ("9999999997", "team", "Ravi (Team)"),
    ("9999999998", "admin", "Admin Kumar"),
    ("9999999999", "super_admin", "Super Admin"),
])
def test_role_login_regression(phone, expected_role, expected_name):
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"phone": phone, "otp": "123456"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["user"]["role"] == expected_role
    assert j["user"]["name"] == expected_name


# ---------------------- Demo numbers: no cooldown enforced ----------------------
def test_demo_number_no_cooldown_multiple_requests():
    # Demo numbers should bypass 30s cooldown (only real SMS path applies it)
    for _ in range(3):
        r = requests.post(f"{API}/auth/request-otp",
                          json={"phone": "9999999996"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["mode"] == "demo"
