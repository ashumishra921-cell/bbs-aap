"""Iteration 3 tests - Auto-assign complaint feature + Team ticket accept flow."""
import os
import pytest
import requests
from filelock import FileLock

# Tests mutate a shared server-side auto_assign flag. Under pytest-xdist we serialize
# every test in this module across workers via a filesystem lock.
_ITER3_LOCK = FileLock("/tmp/iter3_auto_assign.lock")


@pytest.fixture(autouse=True)
def _serialize_iter3():
    with _ITER3_LOCK:
        yield

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://localnet-hub.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


# ---------- Helpers ----------
def _login(phone: str, name: str = None) -> dict:
    """Request+verify OTP for a demo number. Returns {token, user}."""
    r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    otp = r.json().get("otp") or "123456"
    body = {"phone": phone, "otp": otp}
    if name:
        body["name"] = name
    r = requests.post(f"{API}/auth/verify-otp", json=body, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def subscriber():
    return _login("9999999996")


@pytest.fixture(scope="module")
def team():
    return _login("9999999997")


@pytest.fixture(scope="module")
def admin():
    return _login("9999999998")


@pytest.fixture(scope="module")
def super_admin():
    return _login("9999999999")


@pytest.fixture(scope="module", autouse=True)
def ensure_auto_assign_on_at_end(admin):
    """Guarantee auto_assign=true at end of module."""
    yield
    requests.patch(f"{API}/settings", json={"auto_assign": True}, headers=_hdr(admin["token"]))


# ---------- Settings RBAC ----------
class TestSettingsRBAC:
    def test_get_settings_admin_ok(self, admin):
        r = requests.get(f"{API}/settings", headers=_hdr(admin["token"]))
        assert r.status_code == 200
        assert "auto_assign" in r.json()

    def test_get_settings_super_admin_ok(self, super_admin):
        r = requests.get(f"{API}/settings", headers=_hdr(super_admin["token"]))
        assert r.status_code == 200

    def test_get_settings_team_forbidden(self, team):
        r = requests.get(f"{API}/settings", headers=_hdr(team["token"]))
        assert r.status_code == 403

    def test_get_settings_subscriber_forbidden(self, subscriber):
        r = requests.get(f"{API}/settings", headers=_hdr(subscriber["token"]))
        assert r.status_code == 403

    def test_patch_settings_admin_ok(self, admin):
        r = requests.patch(f"{API}/settings", json={"auto_assign": True}, headers=_hdr(admin["token"]))
        assert r.status_code == 200
        assert r.json()["auto_assign"] is True

    def test_patch_settings_team_forbidden(self, team):
        r = requests.patch(f"{API}/settings", json={"auto_assign": False}, headers=_hdr(team["token"]))
        assert r.status_code == 403


# ---------- Auto-assign ON ----------
class TestAutoAssignOn:
    auto_ticket_id = None
    auto_assigned_to = None

    def test_new_complaint_is_auto_assigned(self, subscriber, admin):
        # ensure auto_assign is on
        r = requests.patch(f"{API}/settings", json={"auto_assign": True}, headers=_hdr(admin["token"]))
        assert r.status_code == 200 and r.json()["auto_assign"] is True

        # fetch team members to validate assignment
        t = requests.get(f"{API}/team", headers=_hdr(admin["token"])).json()
        tech_ids = {u["id"] for u in t if u["role"] == "team"}
        assert len(tech_ids) >= 1

        r = requests.post(
            f"{API}/complaints",
            json={"title": "TEST_auto_wifi_slow", "description": "Speed dropped after 8pm", "priority": "high"},
            headers=_hdr(subscriber["token"]),
        )
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["status"] == "assigned"
        assert c["assigned_to"] in tech_ids, f"expected assignment to a team member, got {c['assigned_to']}"
        assert c["assigned_to_name"]
        assert c.get("auto_assigned") is True
        TestAutoAssignOn.auto_ticket_id = c["id"]
        TestAutoAssignOn.auto_assigned_to = c["assigned_to"]

    def test_assigned_team_member_sees_ticket(self, admin):
        """The technician who got the auto-assignment must see the ticket in their list."""
        # login as the assigned team member via phone
        t = requests.get(f"{API}/team", headers=_hdr(admin["token"])).json()
        tech = next((x for x in t if x["id"] == TestAutoAssignOn.auto_assigned_to), None)
        assert tech is not None
        auth = _login(tech["phone"])
        r = requests.get(f"{API}/complaints", headers=_hdr(auth["token"]))
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert TestAutoAssignOn.auto_ticket_id in ids


# ---------- Auto-assign OFF + Team self-claim ----------
class TestAutoAssignOff:
    ticket_id = None
    ticket_no = None

    def test_disable_auto_assign(self, admin):
        r = requests.patch(f"{API}/settings", json={"auto_assign": False}, headers=_hdr(admin["token"]))
        assert r.status_code == 200
        assert r.json()["auto_assign"] is False

    def test_new_complaint_stays_open(self, subscriber):
        r = requests.post(
            f"{API}/complaints",
            json={"title": "TEST_unassigned_router_reboot", "description": "Router keeps rebooting", "priority": "medium"},
            headers=_hdr(subscriber["token"]),
        )
        assert r.status_code == 200
        c = r.json()
        assert c["status"] == "open"
        assert c["assigned_to"] is None
        assert c.get("auto_assigned") is not True
        TestAutoAssignOff.ticket_id = c["id"]
        TestAutoAssignOff.ticket_no = c["ticket_no"]

    def test_team_sees_unassigned_in_list(self, team):
        r = requests.get(f"{API}/complaints", headers=_hdr(team["token"]))
        assert r.status_code == 200
        found = [c for c in r.json() if c["id"] == TestAutoAssignOff.ticket_id]
        assert found and found[0]["assigned_to"] is None and found[0]["status"] == "open"

    def test_team_self_claim_succeeds(self, team):
        r = requests.patch(
            f"{API}/complaints/{TestAutoAssignOff.ticket_id}",
            json={"assigned_to": team["user"]["id"]},
            headers=_hdr(team["token"]),
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["assigned_to"] == team["user"]["id"]
        assert updated["status"] == "assigned"

    def test_team_cannot_assign_to_other(self, subscriber, admin, team):
        # create another unassigned ticket with auto_assign off
        r = requests.post(
            f"{API}/complaints",
            json={"title": "TEST_other_claim_check", "description": "third ticket", "priority": "low"},
            headers=_hdr(subscriber["token"]),
        )
        assert r.status_code == 200
        cid = r.json()["id"]

        # try to assign to admin id (not team role) or someone that's not the team member
        # team can only self-claim; assigning to admin should 403 or 400
        r = requests.patch(
            f"{API}/complaints/{cid}",
            json={"assigned_to": admin["user"]["id"]},
            headers=_hdr(team["token"]),
        )
        assert r.status_code == 403, r.text

    def test_team_cannot_self_claim_already_owned_by_other(self, subscriber, admin, team, super_admin):
        # Only 1 team member seeded. Create another team temporarily to assert the "not your ticket" rule.
        r = requests.post(
            f"{API}/team",
            json={"phone": "9876500011", "name": "TEST_Tech B", "role": "team"},
            headers=_hdr(super_admin["token"]),
        )
        assert r.status_code in (200, 400)  # 400 if pre-existing
        if r.status_code == 200:
            tech_b = r.json()
        else:
            # find existing
            t = requests.get(f"{API}/team", headers=_hdr(admin["token"])).json()
            tech_b = next(x for x in t if x["phone"] == "9876500011")

        # subscriber creates a ticket (auto_assign is off)
        r = requests.post(
            f"{API}/complaints",
            json={"title": "TEST_owned_by_b", "description": "d", "priority": "low"},
            headers=_hdr(subscriber["token"]),
        )
        cid = r.json()["id"]

        # admin assigns to tech_b
        r = requests.patch(
            f"{API}/complaints/{cid}",
            json={"assigned_to": tech_b["id"]},
            headers=_hdr(admin["token"]),
        )
        assert r.status_code == 200

        # team A tries to self-claim -> should 403 (is_self_claim requires unassigned)
        r = requests.patch(
            f"{API}/complaints/{cid}",
            json={"assigned_to": team["user"]["id"]},
            headers=_hdr(team["token"]),
        )
        assert r.status_code == 403

        # cleanup: delete tech_b
        requests.delete(f"{API}/team/{tech_b['id']}", headers=_hdr(super_admin["token"]))


# ---------- Team workflow: In-Progress -> Resolve ----------
class TestTeamWorkflow:
    def test_team_can_progress_and_resolve_own_ticket(self, subscriber, admin):
        # Ensure auto_assign ON so ticket is auto-assigned to some tech
        requests.patch(f"{API}/settings", json={"auto_assign": True}, headers=_hdr(admin["token"]))
        r = requests.post(
            f"{API}/complaints",
            json={"title": "TEST_flow_check", "description": "test flow", "priority": "low"},
            headers=_hdr(subscriber["token"]),
        )
        c = r.json()
        cid = c["id"]
        assigned_to = c["assigned_to"]
        assert assigned_to, "auto_assign failed"

        # login as the technician who was auto-assigned
        t = requests.get(f"{API}/team", headers=_hdr(admin["token"])).json()
        tech = next(x for x in t if x["id"] == assigned_to)
        tech_auth = _login(tech["phone"])
        tech_hdr = _hdr(tech_auth["token"])

        # in_progress
        r = requests.patch(f"{API}/complaints/{cid}", json={"status": "in_progress"}, headers=tech_hdr)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_progress"

        # resolve with note
        r = requests.patch(
            f"{API}/complaints/{cid}",
            json={"status": "resolved", "resolution_note": "Rebooted ONT"},
            headers=tech_hdr,
        )
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "resolved"
        assert j["resolution_note"] == "Rebooted ONT"

    def test_subscriber_sees_own_complaints(self, subscriber):
        r = requests.get(f"{API}/complaints", headers=_hdr(subscriber["token"]))
        assert r.status_code == 200
        items = r.json()
        # must have at least our 3+ test tickets
        assert any(c["title"].startswith("TEST_") for c in items)
        # subscriber should only see own tickets
        assert all(c["user_id"] == subscriber["user"]["id"] for c in items)


# ---------- Admin regression: manual assign still works ----------
class TestAdminManualAssign:
    def test_admin_manual_assign(self, subscriber, admin, team):
        # auto off
        requests.patch(f"{API}/settings", json={"auto_assign": False}, headers=_hdr(admin["token"]))
        r = requests.post(
            f"{API}/complaints",
            json={"title": "TEST_manual_assign", "description": "manual", "priority": "medium"},
            headers=_hdr(subscriber["token"]),
        )
        cid = r.json()["id"]
        assert r.json()["assigned_to"] is None

        r = requests.patch(
            f"{API}/complaints/{cid}",
            json={"assigned_to": team["user"]["id"]},
            headers=_hdr(admin["token"]),
        )
        assert r.status_code == 200
        j = r.json()
        assert j["assigned_to"] == team["user"]["id"]
        assert j["status"] == "assigned"
        assert j.get("auto_assigned") is False
