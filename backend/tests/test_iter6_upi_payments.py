"""Iter 6 — UPI payment with screenshot verification (backend)

RUN SERIALLY: `pytest backend/tests/test_iter6_upi_payments.py -n 0`
Cross-class state (payment id) is shared between TestCreatePayment→TestApprove,
so xdist loadscope splits classes across workers and breaks the chain.

Covers:
- GET /api/payment-config (auth required, returns UPI_ID + payee_name)
- POST /api/payments/upload-screenshot (multipart, image types, ownership)
- GET /api/files/{path}?token=<jwt> (auth via query token, RBAC)
- POST /api/payments (pending only, plan validation, single-pending rule, path ownership)
- GET /api/payments (subscriber sees own only; admin/super see all)
- POST /api/payments/{id}/approve (super_admin only → creates invoice + activates subscription)
- POST /api/payments/{id}/reject (super_admin only, reject_reason stored)
- POST /api/recharge → 410 (removed)
"""
import io
import os
import struct
import zlib
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "https://localnet-hub.preview.emergentagent.com"
API = f"{BASE_URL}/api"

# ---------------- helpers ----------------

def _tiny_png_bytes() -> bytes:
    """Minimal valid 1x1 red PNG."""
    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00" + bytes([255, 0, 0])
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _login(phone: str, name: str | None = None) -> tuple[str, dict]:
    r = requests.post(f"{API}/auth/request-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    body = {"phone": phone, "otp": "123456"}
    if name:
        body["name"] = name
    r = requests.post(f"{API}/auth/verify-otp", json=body, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    return j["token"], j["user"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def tokens():
    sub_tok, sub_user = _login("9999999996", "Amit Sharma")
    admin_tok, admin_user = _login("9999999998")
    super_tok, super_user = _login("9999999999")
    # ensure no stray pending payment for subscriber (super_admin cleans up)
    r = requests.get(f"{API}/payments", headers=_h(super_tok), timeout=15)
    assert r.status_code == 200
    for p in r.json():
        if p["user_id"] == sub_user["id"] and p["status"] == "pending":
            requests.post(f"{API}/payments/{p['id']}/reject", headers=_h(super_tok), json={"reason": "cleanup"}, timeout=15)
    return {
        "sub": (sub_tok, sub_user),
        "admin": (admin_tok, admin_user),
        "super": (super_tok, super_user),
    }


@pytest.fixture(scope="module")
def plan_id(tokens):
    r = requests.get(f"{API}/plans", timeout=15)
    assert r.status_code == 200
    plans = r.json()
    assert plans
    basic = next((p for p in plans if p["name"] == "Basic 50"), plans[0])
    return basic["id"]


# ---------------- Tests: payment-config ----------------

class TestPaymentConfig:
    def test_requires_auth(self):
        r = requests.get(f"{API}/payment-config", timeout=15)
        assert r.status_code == 401

    def test_returns_upi_id(self, tokens):
        r = requests.get(f"{API}/payment-config", headers=_h(tokens["sub"][0]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["upi_id"] == "9312004211-2@ybl"
        assert j["payee_name"]


# ---------------- Tests: upload + files ----------------

class TestUploadAndFiles:
    def test_upload_screenshot_ok(self, tokens):
        sub_tok, _ = tokens["sub"]
        files = {"file": ("shot.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(f"{API}/payments/upload-screenshot", headers=_h(sub_tok), files=files, timeout=60)
        assert r.status_code == 200, r.text
        path = r.json()["path"]
        assert path and "/uploads/" in path
        TestUploadAndFiles.path = path

    def test_upload_rejects_non_image(self, tokens):
        sub_tok, _ = tokens["sub"]
        files = {"file": ("a.txt", b"hello", "text/plain")}
        r = requests.post(f"{API}/payments/upload-screenshot", headers=_h(sub_tok), files=files, timeout=30)
        assert r.status_code == 400

    def test_upload_rejects_empty(self, tokens):
        sub_tok, _ = tokens["sub"]
        files = {"file": ("empty.png", b"", "image/png")}
        r = requests.post(f"{API}/payments/upload-screenshot", headers=_h(sub_tok), files=files, timeout=30)
        assert r.status_code == 400

    def test_get_file_by_owner(self, tokens):
        sub_tok, _ = tokens["sub"]
        r = requests.get(f"{API}/files/{self.path}", params={"token": sub_tok}, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/")

    def test_get_file_forbidden_for_other_subscriber(self, tokens):
        # login as fresh subscriber (10-digit number that isn't demo)
        other_tok, _ = _login("7000012345", "TEST_Other Sub")
        r = requests.get(f"{API}/files/{self.path}", params={"token": other_tok}, timeout=30)
        assert r.status_code == 403

    def test_get_file_ok_for_admin(self, tokens):
        r = requests.get(f"{API}/files/{self.path}", params={"token": tokens["admin"][0]}, timeout=30)
        assert r.status_code == 200

    def test_get_file_ok_for_super(self, tokens):
        r = requests.get(f"{API}/files/{self.path}", params={"token": tokens["super"][0]}, timeout=30)
        assert r.status_code == 200


# ---------------- Tests: create payment ----------------

class TestCreatePayment:
    created_id: str = ""
    screenshot_path: str = ""

    def _upload(self, sub_tok: str) -> str:
        files = {"file": ("shot.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(f"{API}/payments/upload-screenshot", headers=_h(sub_tok), files=files, timeout=60)
        assert r.status_code == 200
        return r.json()["path"]

    def test_bad_plan_404(self, tokens):
        sub_tok, _ = tokens["sub"]
        path = self._upload(sub_tok)
        r = requests.post(f"{API}/payments", headers=_h(sub_tok), json={"plan_id": "nope", "screenshot_path": path, "utr": "T1"}, timeout=30)
        assert r.status_code == 404
        TestCreatePayment.screenshot_path = path  # reuse below (still owned)

    def test_screenshot_not_owned_400(self, tokens, plan_id):
        # subscriber A uploads → subscriber B tries to submit with that path
        sub_tok, _ = tokens["sub"]
        path = self._upload(sub_tok)
        other_tok, _ = _login("7000067890", "TEST_Other Sub2")
        r = requests.post(f"{API}/payments", headers=_h(other_tok), json={"plan_id": plan_id, "screenshot_path": path}, timeout=30)
        assert r.status_code == 400

    def test_create_pending_ok(self, tokens, plan_id):
        sub_tok, _ = tokens["sub"]
        path = self._upload(sub_tok)
        r = requests.post(f"{API}/payments", headers=_h(sub_tok), json={"plan_id": plan_id, "screenshot_path": path, "utr": "TESTUTR123"}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending"
        assert j["utr"] == "TESTUTR123"
        assert j["plan_id"] == plan_id
        TestCreatePayment.created_id = j["id"]

    def test_second_pending_400(self, tokens, plan_id):
        sub_tok, _ = tokens["sub"]
        path = self._upload(sub_tok)
        r = requests.post(f"{API}/payments", headers=_h(sub_tok), json={"plan_id": plan_id, "screenshot_path": path}, timeout=30)
        assert r.status_code == 400


# ---------------- Tests: list RBAC ----------------

class TestListPayments:
    def test_subscriber_sees_own_only(self, tokens):
        sub_tok, sub_user = tokens["sub"]
        r = requests.get(f"{API}/payments", headers=_h(sub_tok), timeout=15)
        assert r.status_code == 200
        for p in r.json():
            assert p["user_id"] == sub_user["id"]

    def test_admin_sees_all(self, tokens):
        r = requests.get(f"{API}/payments", headers=_h(tokens["admin"][0]), timeout=15)
        assert r.status_code == 200
        assert any(p["status"] == "pending" for p in r.json())

    def test_super_sees_all(self, tokens):
        r = requests.get(f"{API}/payments", headers=_h(tokens["super"][0]), timeout=15)
        assert r.status_code == 200
        assert any(p["status"] == "pending" for p in r.json())


# ---------------- Tests: approve ----------------

class TestApprove:
    def test_admin_forbidden(self, tokens):
        pid = TestCreatePayment.created_id
        assert pid
        r = requests.post(f"{API}/payments/{pid}/approve", headers=_h(tokens["admin"][0]), timeout=30)
        assert r.status_code == 403

    def test_super_approve_ok(self, tokens):
        pid = TestCreatePayment.created_id
        r = requests.post(f"{API}/payments/{pid}/approve", headers=_h(tokens["super"][0]), timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["success"] is True
        assert j["invoice"]["payment_mode"] == "upi"
        assert j["invoice"]["upi_id"] == "TESTUTR123"  # utr stored as upi_id
        assert j["invoice"]["status"] == "paid"
        assert j["subscription"]["status"] == "active"
        # verify payment doc updated
        r2 = requests.get(f"{API}/payments", headers=_h(tokens["super"][0]), timeout=15)
        p = next(p for p in r2.json() if p["id"] == pid)
        assert p["status"] == "approved"
        assert p["invoice_id"] == j["invoice"]["id"]

    def test_approve_again_400(self, tokens):
        pid = TestCreatePayment.created_id
        r = requests.post(f"{API}/payments/{pid}/approve", headers=_h(tokens["super"][0]), timeout=30)
        assert r.status_code == 400


# ---------------- Tests: reject ----------------

class TestReject:
    def test_reject_flow(self, tokens, plan_id):
        # subscriber can now create another pending (previous is approved)
        sub_tok, _ = tokens["sub"]
        files = {"file": ("shot.png", _tiny_png_bytes(), "image/png")}
        r = requests.post(f"{API}/payments/upload-screenshot", headers=_h(sub_tok), files=files, timeout=60)
        assert r.status_code == 200
        path = r.json()["path"]
        r = requests.post(f"{API}/payments", headers=_h(sub_tok), json={"plan_id": plan_id, "screenshot_path": path, "utr": "BADUTR"}, timeout=30)
        assert r.status_code == 200
        pid = r.json()["id"]

        # admin cannot reject
        r = requests.post(f"{API}/payments/{pid}/reject", headers=_h(tokens["admin"][0]), json={"reason": "no"}, timeout=15)
        assert r.status_code == 403

        # super rejects
        r = requests.post(f"{API}/payments/{pid}/reject", headers=_h(tokens["super"][0]), json={"reason": "TEST_screenshot unclear"}, timeout=30)
        assert r.status_code == 200
        # verify status
        r2 = requests.get(f"{API}/payments", headers=_h(tokens["super"][0]), timeout=15)
        p = next(p for p in r2.json() if p["id"] == pid)
        assert p["status"] == "rejected"
        assert p["reject_reason"] == "TEST_screenshot unclear"

        # rejecting again → 400
        r = requests.post(f"{API}/payments/{pid}/reject", headers=_h(tokens["super"][0]), json={"reason": "x"}, timeout=15)
        assert r.status_code == 400


# ---------------- Tests: /recharge removed ----------------

class TestRechargeGone:
    def test_recharge_returns_410(self, tokens, plan_id):
        sub_tok, _ = tokens["sub"]
        r = requests.post(f"{API}/recharge", headers=_h(sub_tok), json={"plan_id": plan_id, "upi_id": "x@ybl"}, timeout=15)
        assert r.status_code == 410
