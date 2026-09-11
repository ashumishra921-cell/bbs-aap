"""Iter5: admin close-ticket + full subscriber CRUD + tz-aware timestamps.

Covers review request:
  - admin/super_admin can PATCH /api/complaints/{id} status=resolved (and reopen)
  - POST /api/subscribers with router/security/install/plan+payment (super_admin only)
  - PATCH /api/subscribers/{id} (super_admin) / admin -> 403
  - POST /api/subscribers/{id}/assign-plan {payment_mode:'free'} -> invoice.amount=0
  - GET /api/subscribers shows active_plan for that user
  - Invalid plan_id -> 404
  - GET /api/complaints & /api/invoices created_at is tz-aware (has +00:00 or Z)
  - subscriber recharge (POST /api/recharge) still works with payment_mode='upi'
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SEED = {
    "super_admin": "9999999999",
    "admin": "9999999998",
    "team": "9999999997",
    "subscriber": "9999999996",
}

TZ_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def _login(phone: str):
    r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "123456"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]


def _h(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role, phone in SEED.items():
        tok, user = _login(phone)
        out[role] = {"token": tok, "user": user, "h": _h(tok)}
    return out


@pytest.fixture(scope="module")
def plans():
    r = requests.get(f"{API}/plans", timeout=10)
    assert r.status_code == 200
    return r.json()


# =========================================================================
# 1. Admin / super_admin can CLOSE (resolve) a ticket, and REOPEN it
# =========================================================================
class TestAdminCloseTicket:
    def _new_ticket(self, tokens):
        r = requests.post(f"{API}/complaints", headers=tokens["subscriber"]["h"],
                          json={"title": "TEST close-flow",
                                "description": "iter5 admin close", "priority": "low"},
                          timeout=10)
        assert r.status_code == 200, r.text
        return r.json()

    def test_admin_can_resolve(self, tokens):
        c = self._new_ticket(tokens)
        r = requests.patch(f"{API}/complaints/{c['id']}",
                           headers=tokens["admin"]["h"],
                           json={"status": "resolved", "resolution_note": "TEST closed by admin"},
                           timeout=10)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "resolved"
        assert j["resolution_note"] == "TEST closed by admin"

    def test_admin_can_reopen(self, tokens):
        c = self._new_ticket(tokens)
        # close
        r = requests.patch(f"{API}/complaints/{c['id']}", headers=tokens["admin"]["h"],
                           json={"status": "resolved"}, timeout=10)
        assert r.status_code == 200
        # reopen -> assigned (auto-assigned so it has assigned_to) OR open
        r = requests.patch(f"{API}/complaints/{c['id']}", headers=tokens["admin"]["h"],
                           json={"status": "assigned" if c.get("assigned_to") else "open"},
                           timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] in ("assigned", "open")

    def test_super_admin_can_resolve(self, tokens):
        c = self._new_ticket(tokens)
        r = requests.patch(f"{API}/complaints/{c['id']}",
                           headers=tokens["super_admin"]["h"],
                           json={"status": "resolved"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"

    def test_subscriber_cannot_resolve(self, tokens):
        c = self._new_ticket(tokens)
        r = requests.patch(f"{API}/complaints/{c['id']}",
                           headers=tokens["subscriber"]["h"],
                           json={"status": "resolved"}, timeout=10)
        assert r.status_code == 403


# =========================================================================
# 2. Timezone-aware timestamps on complaints & invoices
# =========================================================================
class TestTimezoneAwareTimestamps:
    def test_complaints_created_at_tz_aware(self, tokens):
        r = requests.get(f"{API}/complaints", headers=tokens["admin"]["h"], timeout=10)
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0, "need at least one complaint (previous tests created some)"
        for c in items[:5]:
            ca = c["created_at"]
            assert isinstance(ca, str), f"created_at must be ISO string, got {type(ca)}"
            assert TZ_RE.search(ca), f"complaint created_at NOT tz-aware: {ca!r}"

    def test_invoices_created_at_tz_aware(self, tokens):
        r = requests.get(f"{API}/invoices", headers=tokens["admin"]["h"], timeout=10)
        assert r.status_code == 200
        items = r.json()
        # may be empty on fresh DB — recharge test below always creates one
        for i in items[:5]:
            ca = i["created_at"]
            assert TZ_RE.search(ca), f"invoice created_at NOT tz-aware: {ca!r}"


# =========================================================================
# 3. Subscriber CRUD (super_admin only) + assign-plan + admin 403
# =========================================================================
class TestSubscriberCRUD:
    created_ids: list = []
    phone = None

    @classmethod
    def _fresh_phone(cls):
        # 10-digit, starts with 7 as spec
        return f"7{int(time.time() * 1000) % 1000000000:09d}"

    def test_create_with_plan_cash(self, tokens, plans):
        plan = plans[0]  # Basic 50
        phone = self._fresh_phone()
        TestSubscriberCRUD.phone = phone
        body = {
            "phone": phone,
            "name": "TEST Ravi Subscriber",
            "address": "TEST 12 Main Rd",
            "router_model": "TP-Link AC1200",
            "router_mac": "AA:BB:CC:11:22:33",
            "security_deposit": 1500,
            "installation_date": "01-01-2026",
            "notes": "TEST landmark near park",
            "plan_id": plan["id"],
            "payment_mode": "cash",
        }
        r = requests.post(f"{API}/subscribers", headers=tokens["super_admin"]["h"], json=body, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["phone"] == phone
        assert d["router_model"] == "TP-Link AC1200"
        assert d["router_mac"] == "AA:BB:CC:11:22:33"
        assert d["security_deposit"] == 1500
        assert d["installation_date"] == "01-01-2026"
        assert d["notes"] == "TEST landmark near park"
        assert "activated" in d
        sub = d["activated"]["subscription"]
        assert sub["status"] == "active"
        assert sub["plan_id"] == plan["id"]
        assert d["activated"]["invoice"]["payment_mode"] == "cash"
        assert d["activated"]["invoice"]["amount"] == plan["price"]
        TestSubscriberCRUD.created_ids.append(d["id"])

    def test_get_subscribers_shows_active_plan(self, tokens, plans):
        r = requests.get(f"{API}/subscribers", headers=tokens["super_admin"]["h"], timeout=10)
        assert r.status_code == 200
        subs = r.json()
        match = [s for s in subs if s["phone"] == TestSubscriberCRUD.phone]
        assert match, f"created subscriber {TestSubscriberCRUD.phone} not in list"
        assert match[0]["active_plan"] == plans[0]["name"]
        assert match[0]["expires_at"] is not None

    def test_admin_cannot_patch_subscriber(self, tokens):
        uid = TestSubscriberCRUD.created_ids[0]
        r = requests.patch(f"{API}/subscribers/{uid}", headers=tokens["admin"]["h"],
                           json={"router_model": "SHOULD_NOT_APPLY"}, timeout=10)
        assert r.status_code == 403

    def test_super_admin_patch_updates(self, tokens):
        uid = TestSubscriberCRUD.created_ids[0]
        r = requests.patch(f"{API}/subscribers/{uid}", headers=tokens["super_admin"]["h"],
                           json={"router_model": "TEST-Netgear-R7000", "notes": "TEST updated"},
                           timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["router_model"] == "TEST-Netgear-R7000"
        assert d["notes"] == "TEST updated"

    def test_assign_plan_free_invoice_zero(self, tokens, plans):
        uid = TestSubscriberCRUD.created_ids[0]
        plan = plans[1]
        r = requests.post(f"{API}/subscribers/{uid}/assign-plan",
                          headers=tokens["super_admin"]["h"],
                          json={"plan_id": plan["id"], "payment_mode": "free"},
                          timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["invoice"]["amount"] == 0.0
        assert d["invoice"]["payment_mode"] == "free"
        assert d["subscription"]["status"] == "active"
        assert d["subscription"]["plan_id"] == plan["id"]

    def test_assign_plan_invalid_id_404(self, tokens):
        uid = TestSubscriberCRUD.created_ids[0]
        r = requests.post(f"{API}/subscribers/{uid}/assign-plan",
                          headers=tokens["super_admin"]["h"],
                          json={"plan_id": "does-not-exist", "payment_mode": "cash"},
                          timeout=10)
        assert r.status_code == 404

    def test_create_with_invalid_plan_404(self, tokens):
        body = {
            "phone": self._fresh_phone(),
            "name": "TEST BadPlan",
            "plan_id": "invalid-uuid-xyz",
            "payment_mode": "cash",
        }
        r = requests.post(f"{API}/subscribers", headers=tokens["super_admin"]["h"], json=body, timeout=10)
        assert r.status_code == 404

    def test_admin_cannot_create_subscriber(self, tokens):
        body = {"phone": self._fresh_phone(), "name": "TEST admin-should-fail"}
        r = requests.post(f"{API}/subscribers", headers=tokens["admin"]["h"], json=body, timeout=10)
        assert r.status_code == 403

    def test_admin_cannot_delete_subscriber(self, tokens):
        uid = TestSubscriberCRUD.created_ids[0]
        r = requests.delete(f"{API}/subscribers/{uid}", headers=tokens["admin"]["h"], timeout=10)
        assert r.status_code == 403

    def test_super_admin_can_delete_and_cleanup(self, tokens):
        # cleanup all created
        for uid in list(TestSubscriberCRUD.created_ids):
            r = requests.delete(f"{API}/subscribers/{uid}", headers=tokens["super_admin"]["h"], timeout=10)
            assert r.status_code == 200
        TestSubscriberCRUD.created_ids.clear()
        # verify gone
        r = requests.get(f"{API}/subscribers", headers=tokens["super_admin"]["h"], timeout=10)
        phones = {s["phone"] for s in r.json()}
        assert TestSubscriberCRUD.phone not in phones


# =========================================================================
# 4. Recharge still works for subscriber (UPI)
# =========================================================================
class TestRecharge:
    def test_subscriber_recharge_upi(self, tokens, plans):
        plan = plans[0]
        r = requests.post(f"{API}/recharge", headers=tokens["subscriber"]["h"],
                          json={"plan_id": plan["id"], "upi_id": "test@upi"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["invoice"]["payment_mode"] == "upi"
        assert d["invoice"]["status"] == "paid"
        assert d["invoice"]["amount"] == plan["price"]
        assert TZ_RE.search(d["invoice"]["created_at"]), f"tz missing on new invoice: {d['invoice']['created_at']!r}"
        assert d["subscription"]["status"] == "active"
