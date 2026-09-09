"""Backend tests for Broadband Solutions 24x7"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://localnet-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SEED = {
    "super_admin": "9999999999",
    "admin": "9999999998",
    "team": "9999999997",
    "subscriber": "9999999996",
}

_tokens = {}
_users = {}


def _login(phone: str, name: str = None):
    if phone in _tokens:
        return _tokens[phone], _users[phone]
    r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    body = {"phone": phone, "otp": "123456"}
    if name:
        body["name"] = name
    r = requests.post(f"{API}/auth/verify-otp", json=body, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    _tokens[phone] = data["token"]
    _users[phone] = data["user"]
    return data["token"], data["user"]


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Health ----------------
def test_health():
    r = requests.get(f"{API}/", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------------- Auth ----------------
def test_request_otp_existing_phone():
    r = requests.post(f"{API}/auth/request-otp", json={"phone": SEED["subscriber"]}, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j["is_new_user"] is False
    assert j["otp"] == "123456"


def test_request_otp_new_phone():
    r = requests.post(f"{API}/auth/request-otp", json={"phone": "8888800001"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["is_new_user"] is True


def test_verify_otp_wrong():
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"phone": SEED["subscriber"], "otp": "000000"}, timeout=10)
    assert r.status_code == 400


def test_verify_otp_seeded_roles():
    for role, phone in SEED.items():
        r = requests.post(f"{API}/auth/verify-otp",
                          json={"phone": phone, "otp": "123456"}, timeout=10)
        assert r.status_code == 200, f"{role} {r.text}"
        j = r.json()
        assert "token" in j and "user" in j
        assert j["user"]["role"] == role


def test_verify_otp_new_user_signup():
    phone = f"77777{int(time.time()) % 100000:05d}"
    r = requests.post(f"{API}/auth/verify-otp",
                      json={"phone": phone, "otp": "123456", "name": "TEST NewUser"}, timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j["user"]["role"] == "subscriber"
    assert j["user"]["name"] == "TEST NewUser"


# ---------------- Plans ----------------
def test_list_plans():
    r = requests.get(f"{API}/plans", timeout=10)
    assert r.status_code == 200
    plans = r.json()
    assert isinstance(plans, list)
    assert len(plans) >= 4
    names = [p["name"] for p in plans]
    for n in ["Basic 50", "Family 100", "Premium 200", "Unlimited Pro"]:
        assert n in names


# ---------------- Recharge + Invoice + Subscription ----------------
def test_recharge_flow_and_isolation():
    tok_sub, sub_user = _login(SEED["subscriber"])
    plans = requests.get(f"{API}/plans", timeout=10).json()
    plan = plans[0]
    r = requests.post(f"{API}/recharge",
                      headers=_h(tok_sub),
                      json={"plan_id": plan["id"], "upi_id": "test@upi"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["invoice"]["status"] == "paid"
    assert j["invoice"]["amount"] == plan["price"]
    invoice_id = j["invoice"]["id"]

    # subscription
    r = requests.get(f"{API}/me/subscription", headers=_h(tok_sub), timeout=10)
    assert r.status_code == 200
    sub = r.json()
    assert sub is not None
    assert sub["plan_id"] == plan["id"]
    assert sub["status"] == "active"

    # invoices - subscriber sees only own
    r = requests.get(f"{API}/invoices", headers=_h(tok_sub), timeout=10)
    assert r.status_code == 200
    invs = r.json()
    assert all(i["user_id"] == sub_user["id"] for i in invs)
    assert any(i["id"] == invoice_id for i in invs)

    # verify invoice GET
    r = requests.get(f"{API}/invoices/{invoice_id}", headers=_h(tok_sub), timeout=10)
    assert r.status_code == 200
    assert r.json()["id"] == invoice_id


# ---------------- Complaints ----------------
_complaint_id = {"id": None}


def test_subscriber_create_complaint():
    tok, u = _login(SEED["subscriber"])
    r = requests.post(f"{API}/complaints", headers=_h(tok),
                      json={"title": "TEST Slow net", "description": "Slow speed", "priority": "high"},
                      timeout=10)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["status"] == "open"
    assert c["user_id"] == u["id"]
    _complaint_id["id"] = c["id"]


def test_complaint_list_role_isolation():
    tok_sub, _ = _login(SEED["subscriber"])
    r = requests.get(f"{API}/complaints", headers=_h(tok_sub), timeout=10)
    assert r.status_code == 200
    for c in r.json():
        assert c["user_id"] == _users[SEED["subscriber"]]["id"]

    tok_admin, _ = _login(SEED["admin"])
    r = requests.get(f"{API}/complaints", headers=_h(tok_admin), timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    tok_team, team_user = _login(SEED["team"])
    r = requests.get(f"{API}/complaints", headers=_h(tok_team), timeout=10)
    assert r.status_code == 200
    for c in r.json():
        assert c.get("assigned_to") == team_user["id"]


def test_admin_assign_complaint_to_team():
    tok_admin, _ = _login(SEED["admin"])
    tok_team, team_user = _login(SEED["team"])
    cid = _complaint_id["id"]
    r = requests.patch(f"{API}/complaints/{cid}", headers=_h(tok_admin),
                       json={"assigned_to": team_user["id"]}, timeout=10)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["assigned_to"] == team_user["id"]
    assert c["status"] == "assigned"


def test_team_updates_status():
    tok_team, _ = _login(SEED["team"])
    cid = _complaint_id["id"]
    r = requests.patch(f"{API}/complaints/{cid}", headers=_h(tok_team),
                       json={"status": "in_progress"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    r = requests.patch(f"{API}/complaints/{cid}", headers=_h(tok_team),
                       json={"status": "resolved", "resolution_note": "TEST fixed"},
                       timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["resolution_note"] == "TEST fixed"


def test_team_cannot_update_unassigned():
    """Create a new complaint (unassigned) and ensure team cannot update it"""
    tok_sub, _ = _login(SEED["subscriber"])
    r = requests.post(f"{API}/complaints", headers=_h(tok_sub),
                      json={"title": "TEST unassigned", "description": "x"}, timeout=10)
    cid = r.json()["id"]
    tok_team, _ = _login(SEED["team"])
    r = requests.patch(f"{API}/complaints/{cid}", headers=_h(tok_team),
                       json={"status": "in_progress"}, timeout=10)
    assert r.status_code == 403


# ---------------- Team management ----------------
def test_admin_creates_team_member():
    tok_admin, _ = _login(SEED["admin"])
    phone = f"7000{int(time.time()) % 1000000:06d}"
    r = requests.post(f"{API}/team", headers=_h(tok_admin),
                      json={"phone": phone, "name": "TEST Team Guy", "role": "team"},
                      timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "team"


def test_admin_cannot_create_admin():
    tok_admin, _ = _login(SEED["admin"])
    phone = f"7100{int(time.time()) % 1000000:06d}"
    r = requests.post(f"{API}/team", headers=_h(tok_admin),
                      json={"phone": phone, "name": "TEST Bad Admin", "role": "admin"},
                      timeout=10)
    assert r.status_code == 403


def test_super_admin_can_create_admin():
    tok_super, _ = _login(SEED["super_admin"])
    phone = f"7200{int(time.time()) % 1000000:06d}"
    r = requests.post(f"{API}/team", headers=_h(tok_super),
                      json={"phone": phone, "name": "TEST New Admin", "role": "admin"},
                      timeout=10)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


# ---------------- Admin metrics & subscribers ----------------
def test_admin_metrics():
    tok_admin, _ = _login(SEED["admin"])
    r = requests.get(f"{API}/admin/metrics", headers=_h(tok_admin), timeout=10)
    assert r.status_code == 200
    m = r.json()
    for k in ["subscribers", "team_members", "active_subscriptions",
              "open_complaints", "resolved_complaints", "total_revenue"]:
        assert k in m
    assert m["subscribers"] >= 1


def test_admin_list_subscribers():
    tok_admin, _ = _login(SEED["admin"])
    r = requests.get(f"{API}/subscribers", headers=_h(tok_admin), timeout=10)
    assert r.status_code == 200
    subs = r.json()
    assert isinstance(subs, list)
    assert any(s["phone"] == SEED["subscriber"] for s in subs)


# ---------------- Chat ----------------
def test_chat_hindi_reply():
    tok, _ = _login(SEED["subscriber"])
    r = requests.post(f"{API}/chat", headers=_h(tok),
                      json={"message": "मेरा इंटरनेट धीमा है"}, timeout=60)
    assert r.status_code == 200, r.text
    reply = r.json().get("reply", "")
    assert isinstance(reply, str) and len(reply) > 0


def test_chat_history():
    tok, _ = _login(SEED["subscriber"])
    r = requests.get(f"{API}/chat/history", headers=_h(tok), timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 2  # at least user + assistant from prev test
