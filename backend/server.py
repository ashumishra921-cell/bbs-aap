"""Broadband Solutions 24x7 - Backend"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, UploadFile, File
from fastapi.responses import StreamingResponse, Response
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import asyncio
import logging
import uuid
import jwt
import httpx
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url, tz_aware=True)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET', 'dev_secret')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
MOCK_OTP = os.environ.get('DEMO_OTP', '123456')
DEMO_NUMBERS = {p.strip() for p in os.environ.get('DEMO_NUMBERS', '9999999996,9999999997,9999999998,9999999999').split(',') if p.strip()}
MSG91_AUTH_KEY = os.environ.get('MSG91_AUTH_KEY', '').strip()
MSG91_TEMPLATE_ID = os.environ.get('MSG91_TEMPLATE_ID', '').strip()
MSG91_DLT_TE_ID = os.environ.get('MSG91_DLT_TE_ID', '').strip()
SMS_ENABLED = bool(MSG91_AUTH_KEY and MSG91_TEMPLATE_ID)
OTP_RESEND_COOLDOWN_SEC = 30
_otp_last_sent: dict[str, datetime] = {}

app = FastAPI(title="Broadband Solutions 24x7")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------- Models ----------------------
Role = Literal["subscriber", "team", "admin", "super_admin"]


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phone: str
    name: str
    role: Role = "subscriber"
    address: Optional[str] = None
    router_model: Optional[str] = None
    router_mac: Optional[str] = None
    security_deposit: Optional[float] = None
    installation_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Plan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    speed_mbps: int
    data_gb: int  # 0 = unlimited
    validity_days: int
    price: float
    description: str


class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    plan_id: str
    plan_name: str
    speed_mbps: int
    data_gb: int
    used_gb: float = 0.0
    started_at: datetime
    expires_at: datetime
    status: Literal["active", "expired"] = "active"


class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invoice_no: str
    user_id: str
    user_name: str
    user_phone: str
    plan_id: str
    plan_name: str
    amount: float
    upi_id: Optional[str] = None
    payment_mode: Literal["upi", "cash", "free"] = "upi"
    status: Literal["pending", "paid", "failed"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    paid_at: Optional[datetime] = None


class Complaint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticket_no: str
    user_id: str
    user_name: str
    user_phone: str
    title: str
    description: str
    priority: Literal["low", "medium", "high"] = "medium"
    status: Literal["open", "assigned", "in_progress", "resolved"] = "open"
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    resolution_note: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------- Request Schemas ----------------------
class RequestOtpBody(BaseModel):
    phone: str


class VerifyOtpBody(BaseModel):
    phone: str
    otp: str
    name: Optional[str] = None  # for new subscribers


class CreateComplaintBody(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high"] = "medium"
    lat: Optional[float] = None
    lng: Optional[float] = None


class UpdateComplaintBody(BaseModel):
    status: Optional[Literal["open", "assigned", "in_progress", "resolved"]] = None
    assigned_to: Optional[str] = None
    resolution_note: Optional[str] = None


class RechargeBody(BaseModel):
    plan_id: str
    upi_id: str


class CreatePlanBody(BaseModel):
    name: str
    speed_mbps: int
    data_gb: int
    validity_days: int
    price: float
    description: str


class CreateTeamMemberBody(BaseModel):
    phone: str
    name: str
    role: Literal["team", "admin"] = "team"


class CreateSubscriberBody(BaseModel):
    phone: str
    name: str
    address: Optional[str] = None
    router_model: Optional[str] = None
    router_mac: Optional[str] = None
    security_deposit: Optional[float] = None
    installation_date: Optional[str] = None
    notes: Optional[str] = None
    plan_id: Optional[str] = None
    payment_mode: Literal["cash", "upi", "free"] = "cash"


class UpdateSubscriberBody(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    router_model: Optional[str] = None
    router_mac: Optional[str] = None
    security_deposit: Optional[float] = None
    installation_date: Optional[str] = None
    notes: Optional[str] = None


class AssignPlanBody(BaseModel):
    plan_id: str
    payment_mode: Literal["cash", "upi", "free"] = "cash"


class ChatBody(BaseModel):
    message: str


# ---------------------- Helpers ----------------------
def make_token(user_id: str) -> str:
    payload = {"sub": user_id, "iat": datetime.now(timezone.utc).timestamp()}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(*allowed: Role):
    async def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return _dep


def clean(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ---------------------- Health (root-level, used by deployment probes) ----------------------
@app.get("/")
@app.get("/health")
@api_router.get("/health")
async def health():
    return {"status": "ok", "app": "Broadband Solutions 24x7"}


# ---------------------- Auth ----------------------
@api_router.get("/")
async def root():
    return {"app": "Broadband Solutions 24x7", "status": "ok"}


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise HTTPException(status_code=400, detail="कृपया सही 10 अंकों का मोबाइल नंबर दर्ज करें")
    return digits


def uses_mock_otp(phone: str) -> bool:
    return (not SMS_ENABLED) or phone in DEMO_NUMBERS


async def msg91_send_otp(phone: str) -> None:
    params = {
        "template_id": MSG91_TEMPLATE_ID,
        "mobile": f"91{phone}",
        "authkey": MSG91_AUTH_KEY,
        "otp_length": 6,
        "otp_expiry": 5,
    }
    if MSG91_DLT_TE_ID:
        params["DLT_TE_ID"] = MSG91_DLT_TE_ID
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post("https://control.msg91.com/api/v5/otp", params=params, headers={"Accept": "application/json"})
        data = r.json()
    except Exception as e:
        logger.error(f"MSG91 send failed: {e}")
        raise HTTPException(status_code=502, detail="SMS भेजने में समस्या, कृपया बाद में प्रयास करें")
    if r.status_code >= 400 or str(data.get("type", "")).lower() == "error":
        logger.error(f"MSG91 rejected send: {data}")
        raise HTTPException(status_code=502, detail="SMS भेजने में समस्या, कृपया बाद में प्रयास करें")


async def msg91_verify_otp(phone: str, otp: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(
                "https://control.msg91.com/api/v5/otp/verify",
                params={"mobile": f"91{phone}", "otp": otp},
                headers={"authkey": MSG91_AUTH_KEY, "Accept": "application/json"},
            )
        data = r.json()
    except Exception as e:
        logger.error(f"MSG91 verify failed: {e}")
        raise HTTPException(status_code=502, detail="OTP जांच में समस्या, कृपया बाद में प्रयास करें")
    if r.status_code >= 400 or str(data.get("type", "")).lower() != "success":
        raise HTTPException(status_code=400, detail="गलत या समाप्त OTP")


@api_router.get("/auth/config")
async def auth_config():
    return {"sms_enabled": SMS_ENABLED, "demo_otp": None if SMS_ENABLED else MOCK_OTP, "resend_cooldown_sec": OTP_RESEND_COOLDOWN_SEC}


@api_router.post("/auth/request-otp")
async def request_otp(body: RequestOtpBody):
    phone = normalize_phone(body.phone)
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    mock = uses_mock_otp(phone)
    now = datetime.now(timezone.utc)
    last = _otp_last_sent.get(phone)
    if not mock and last and (now - last).total_seconds() < OTP_RESEND_COOLDOWN_SEC:
        wait = OTP_RESEND_COOLDOWN_SEC - int((now - last).total_seconds())
        raise HTTPException(status_code=429, detail=f"कृपया {wait} सेकंड बाद पुनः प्रयास करें")
    if not mock:
        await msg91_send_otp(phone)
    _otp_last_sent[phone] = now
    return {
        "success": True,
        "mode": "demo" if mock else "sms",
        "message": f"Demo OTP: {MOCK_OTP}" if mock else "OTP SMS भेजा गया",
        "otp": MOCK_OTP if mock else None,
        "is_new_user": user is None,
    }


@api_router.post("/auth/verify-otp")
async def verify_otp(body: VerifyOtpBody):
    phone = normalize_phone(body.phone)
    if uses_mock_otp(phone):
        if body.otp != MOCK_OTP:
            raise HTTPException(status_code=400, detail="गलत OTP")
    else:
        await msg91_verify_otp(phone, body.otp)
    body.phone = phone
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    if not user:
        # new subscriber signup
        new_user = User(phone=body.phone, name=body.name or f"User {body.phone[-4:]}", role="subscriber")
        await db.users.insert_one(new_user.model_dump())
        user = new_user.model_dump()
    token = make_token(user["id"])
    return {"token": token, "user": user}


@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user


# ---------------------- Plans ----------------------
class UpdatePlanBody(BaseModel):
    name: Optional[str] = None
    speed_mbps: Optional[int] = None
    data_gb: Optional[int] = None
    validity_days: Optional[int] = None
    price: Optional[float] = None
    description: Optional[str] = None
    active: Optional[bool] = None


@api_router.get("/plans")
async def list_plans(all: bool = False, authorization: Optional[str] = Header(None)):
    q: dict = {}
    if all:
        user = await get_current_user(authorization)
        if user["role"] not in ("admin", "super_admin"):
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        q = {"active": {"$ne": False}}
    return await db.plans.find(q, {"_id": 0}).sort("price", 1).to_list(500)


@api_router.post("/plans")
async def create_plan(body: CreatePlanBody, user: dict = Depends(require_role("super_admin"))):
    plan = Plan(**body.model_dump())
    doc = {**plan.model_dump(), "active": True}
    await db.plans.insert_one(doc)
    return clean(doc)


@api_router.patch("/plans/{plan_id}")
async def update_plan(plan_id: str, body: UpdatePlanBody, user: dict = Depends(require_role("super_admin"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    res = await db.plans.update_one({"id": plan_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plan not found")
    return clean(await db.plans.find_one({"id": plan_id}, {"_id": 0}))


@api_router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, user: dict = Depends(require_role("super_admin"))):
    if await db.subscriptions.find_one({"plan_id": plan_id, "status": "active"}):
        # keep history intact: hide instead of hard delete
        await db.plans.update_one({"id": plan_id}, {"$set": {"active": False}})
        return {"success": True, "hidden": True}
    await db.plans.delete_one({"id": plan_id})
    return {"success": True}


# ---------------------- Recharge / Subscription ----------------------
@api_router.get("/me/subscription")
async def my_subscription(user: dict = Depends(get_current_user)):
    sub = await db.subscriptions.find_one({"user_id": user["id"], "status": "active"}, {"_id": 0}, sort=[("expires_at", -1)])
    return sub


async def activate_plan(user: dict, plan: dict, payment_mode: str, upi_id: Optional[str] = None) -> dict:
    now = datetime.now(timezone.utc)
    invoice_no = f"INV-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    invoice = Invoice(
        invoice_no=invoice_no,
        user_id=user["id"],
        user_name=user["name"],
        user_phone=user["phone"],
        plan_id=plan["id"],
        plan_name=plan["name"],
        amount=0.0 if payment_mode == "free" else plan["price"],
        upi_id=upi_id,
        payment_mode=payment_mode,
        status="paid",
        paid_at=now,
    )
    await db.invoices.insert_one(invoice.model_dump())
    await db.subscriptions.update_many({"user_id": user["id"], "status": "active"}, {"$set": {"status": "expired"}})
    sub = Subscription(
        user_id=user["id"],
        plan_id=plan["id"],
        plan_name=plan["name"],
        speed_mbps=plan["speed_mbps"],
        data_gb=plan["data_gb"],
        used_gb=0.0,
        started_at=now,
        expires_at=now + timedelta(days=plan["validity_days"]),
        status="active",
    )
    await db.subscriptions.insert_one(sub.model_dump())
    return {"invoice": invoice.model_dump(), "subscription": sub.model_dump()}


@api_router.post("/recharge")
async def recharge(body: RechargeBody, user: dict = Depends(get_current_user)):
    raise HTTPException(status_code=410, detail="Instant recharge disabled. Pay via UPI and upload screenshot for verification.")


# ---------------------- UPI payment requests (screenshot verification) ----------------------
UPI_ID = os.environ.get("UPI_ID", "9312004211-2@ybl")
UPI_PAYEE_NAME = os.environ.get("UPI_PAYEE_NAME", "Broadband Solutions 24x7")
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
STORAGE_APP = "broadband-solutions-247"
MAX_SCREENSHOT_BYTES = 6 * 1024 * 1024
_storage_key: Optional[str] = None


def init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _storage_call(method: str, path: str, **kw) -> requests.Response:
    global _storage_key
    key = init_storage()
    resp = requests.request(method, f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, **kw.pop("headers", {})}, **kw)
    if resp.status_code == 503:  # stale key → re-init once
        _storage_key = None
        key = init_storage()
        resp = requests.request(method, f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key, **kw.pop("headers", {})}, **kw)
    return resp


def put_object(path: str, data: bytes, content_type: str) -> dict:
    resp = _storage_call("PUT", path, headers={"Content-Type": content_type}, data=data, timeout=120)
    if resp.status_code == 402:
        raise HTTPException(status_code=402, detail="Storage credits exhausted. Please contact support.")
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    resp = _storage_call("GET", path, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


class PaymentRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    user_phone: str
    plan_id: str
    plan_name: str
    amount: float
    screenshot_path: str
    utr: Optional[str] = None
    status: Literal["pending", "approved", "rejected"] = "pending"
    reject_reason: Optional[str] = None
    invoice_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreatePaymentBody(BaseModel):
    plan_id: str
    screenshot_path: str
    utr: Optional[str] = None


class RejectBody(BaseModel):
    reason: Optional[str] = None


@api_router.get("/payment-config")
async def payment_config(user: dict = Depends(get_current_user)):
    return {"upi_id": UPI_ID, "payee_name": UPI_PAYEE_NAME}


@api_router.post("/payments/upload-screenshot")
async def upload_screenshot(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(status_code=413, detail="Screenshot 6MB से छोटा होना चाहिए")
    ctype = (file.content_type or "image/jpeg").lower()
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=400, detail="केवल image फ़ाइल अपलोड करें")
    ext = {"image/png": "png", "image/webp": "webp", "image/heic": "heic"}.get(ctype, "jpg")
    path = f"{STORAGE_APP}/uploads/{user['id']}/{uuid.uuid4()}.{ext}"
    try:
        result = await run_in_threadpool(put_object, path, data, ctype)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screenshot upload failed: {e}")
        raise HTTPException(status_code=502, detail="Upload failed, कृपया पुनः प्रयास करें")
    await db.files.insert_one({"path": result["path"], "owner_id": user["id"], "content_type": ctype, "size": len(data), "created_at": datetime.now(timezone.utc)})
    return {"path": result["path"]}


@api_router.get("/files/{path:path}")
async def get_file(path: str, token: Optional[str] = None, authorization: Optional[str] = Header(None)):
    if not authorization and token:
        authorization = f"Bearer {token}"
    user = await get_current_user(authorization)
    meta = await db.files.find_one({"path": path}, {"_id": 0})
    if not meta:
        raise HTTPException(status_code=404, detail="File not found")
    if user["role"] not in ("admin", "super_admin") and meta["owner_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        content, ctype = await run_in_threadpool(get_object, path)
    except Exception as e:
        logger.error(f"File fetch failed: {e}")
        raise HTTPException(status_code=502, detail="File unavailable")
    return Response(content=content, media_type=ctype, headers={"Cache-Control": "private, max-age=3600"})


@api_router.post("/payments")
async def create_payment(body: CreatePaymentBody, user: dict = Depends(get_current_user)):
    plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    meta = await db.files.find_one({"path": body.screenshot_path, "owner_id": user["id"]}, {"_id": 0})
    if not meta:
        raise HTTPException(status_code=400, detail="Screenshot अपलोड करें")
    if await db.payments.find_one({"user_id": user["id"], "status": "pending"}):
        raise HTTPException(status_code=400, detail="आपका एक payment पहले से verification में है")
    p = PaymentRequest(
        user_id=user["id"], user_name=user["name"], user_phone=user["phone"],
        plan_id=plan["id"], plan_name=plan["name"], amount=plan["price"],
        screenshot_path=body.screenshot_path, utr=(body.utr or "").strip() or None,
    )
    await db.payments.insert_one(p.model_dump())
    return p.model_dump()


@api_router.get("/payments")
async def list_payments(user: dict = Depends(get_current_user)):
    q = {} if user["role"] in ("admin", "super_admin") else {"user_id": user["id"]}
    return await db.payments.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@api_router.post("/payments/{pid}/approve")
async def approve_payment(pid: str, user: dict = Depends(require_role("super_admin"))):
    p = await db.payments.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already reviewed")
    target = await db.users.find_one({"id": p["user_id"]}, {"_id": 0})
    plan = await db.plans.find_one({"id": p["plan_id"]}, {"_id": 0})
    if not target or not plan:
        raise HTTPException(status_code=404, detail="User or plan missing")
    activated = await activate_plan(target, plan, "upi", p.get("utr"))
    now = datetime.now(timezone.utc)
    await db.payments.update_one({"id": pid}, {"$set": {"status": "approved", "invoice_id": activated["invoice"]["id"], "reviewed_by": user["name"], "reviewed_at": now}})
    return {"success": True, **activated}


@api_router.post("/payments/{pid}/reject")
async def reject_payment(pid: str, body: RejectBody, user: dict = Depends(require_role("super_admin"))):
    p = await db.payments.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    if p["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already reviewed")
    await db.payments.update_one({"id": pid}, {"$set": {"status": "rejected", "reject_reason": (body.reason or "").strip() or None, "reviewed_by": user["name"], "reviewed_at": datetime.now(timezone.utc)}})
    return {"success": True}


# ---------------------- Invoices ----------------------
@api_router.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    q = {} if user["role"] in ("admin", "super_admin") else {"user_id": user["id"]}
    items = await db.invoices.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api_router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == "subscriber" and inv["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return inv


# ---------------------- Complaints ----------------------
async def get_setting(key: str, default):
    doc = await db.settings.find_one({"key": key}, {"_id": 0})
    return doc["value"] if doc else default


import math

LOCATION_FRESH_MINUTES = 120


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fresh_location(u: dict) -> Optional[dict]:
    loc = u.get("location")
    if not loc or not loc.get("updated_at"):
        return None
    if datetime.now(timezone.utc) - loc["updated_at"] > timedelta(minutes=LOCATION_FRESH_MINUTES):
        return None
    return loc


async def pick_technician(lat: Optional[float] = None, lng: Optional[float] = None) -> Optional[dict]:
    """Nearest technician with a fresh location if complaint has coordinates; otherwise least loaded."""
    techs = await db.users.find({"role": "team"}, {"_id": 0, "id": 1, "name": 1, "location": 1}).to_list(500)
    if not techs:
        return None
    loads = {t["id"]: 0 for t in techs}
    async for row in db.complaints.aggregate([
        {"$match": {"assigned_to": {"$in": list(loads)}, "status": {"$in": ["assigned", "in_progress"]}}},
        {"$group": {"_id": "$assigned_to", "n": {"$sum": 1}}},
    ]):
        loads[row["_id"]] = row["n"]
    if lat is not None and lng is not None:
        located = [(haversine_km(lat, lng, l["lat"], l["lng"]), t) for t in techs if (l := fresh_location(t))]
        if located:
            dist, t = min(located, key=lambda x: (x[0], loads[x[1]["id"]]))
            return {**t, "distance_km": round(dist, 1)}
    return min(techs, key=lambda t: loads[t["id"]])


async def pick_least_loaded_technician() -> Optional[dict]:
    return await pick_technician()


@api_router.get("/settings")
async def get_settings(user: dict = Depends(require_role("admin", "super_admin"))):
    return {"auto_assign": await get_setting("auto_assign", True)}


class SettingsBody(BaseModel):
    auto_assign: Optional[bool] = None


@api_router.patch("/settings")
async def update_settings(body: SettingsBody, user: dict = Depends(require_role("admin", "super_admin"))):
    if body.auto_assign is not None:
        await db.settings.update_one({"key": "auto_assign"}, {"$set": {"value": body.auto_assign}}, upsert=True)
    return {"auto_assign": await get_setting("auto_assign", True)}


@api_router.post("/complaints")
async def create_complaint(body: CreateComplaintBody, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    ticket_no = f"TKT-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    c = Complaint(
        ticket_no=ticket_no,
        user_id=user["id"],
        user_name=user["name"],
        user_phone=user["phone"],
        title=body.title,
        description=body.description,
        priority=body.priority,
        status="open",
    )
    doc = c.model_dump()
    if body.lat is not None and body.lng is not None:
        doc["location"] = {"lat": body.lat, "lng": body.lng}
    if await get_setting("auto_assign", True):
        tech = await pick_technician(body.lat, body.lng)
        if tech:
            doc.update({"assigned_to": tech["id"], "assigned_to_name": tech["name"], "status": "assigned", "auto_assigned": True})
    await db.complaints.insert_one(doc)
    return clean(doc)


@api_router.get("/complaints")
async def list_complaints(user: dict = Depends(get_current_user)):
    role = user["role"]
    if role == "subscriber":
        q = {"user_id": user["id"]}
    elif role == "team":
        # own tickets + unassigned open tickets (any technician can accept)
        q = {"$or": [{"assigned_to": user["id"]}, {"assigned_to": None, "status": "open"}]}
    else:
        q = {}
    items = await db.complaints.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api_router.patch("/complaints/{cid}")
async def update_complaint(cid: str, body: UpdateComplaintBody, user: dict = Depends(get_current_user)):
    c = await db.complaints.find_one({"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    role = user["role"]
    updates = {}
    if body.assigned_to is not None:
        is_self_claim = role == "team" and body.assigned_to == user["id"] and not c.get("assigned_to")
        if role not in ("admin", "super_admin") and not is_self_claim:
            raise HTTPException(status_code=403, detail="Only admin can assign")
        member = await db.users.find_one({"id": body.assigned_to}, {"_id": 0})
        if not member or member["role"] != "team":
            raise HTTPException(status_code=400, detail="Invalid team member")
        updates["assigned_to"] = member["id"]
        updates["assigned_to_name"] = member["name"]
        updates["auto_assigned"] = False
        if not body.status:
            updates["status"] = "assigned"
    if body.status is not None:
        if role == "subscriber":
            raise HTTPException(status_code=403, detail="Forbidden")
        if role == "team" and c.get("assigned_to") not in (None, user["id"]):
            raise HTTPException(status_code=403, detail="Not your ticket")
        if role == "team" and not c.get("assigned_to"):
            updates["assigned_to"] = user["id"]
            updates["assigned_to_name"] = user["name"]
        updates["status"] = body.status
    if body.resolution_note is not None:
        updates["resolution_note"] = body.resolution_note
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.complaints.update_one({"id": cid}, {"$set": updates})
    return clean(await db.complaints.find_one({"id": cid}, {"_id": 0}))


# ---------------------- Team / Users management ----------------------
@api_router.get("/team")
async def list_team(lat: Optional[float] = None, lng: Optional[float] = None, user: dict = Depends(require_role("admin", "super_admin"))):
    items = await db.users.find({"role": {"$in": ["team", "admin"]}}, {"_id": 0}).to_list(500)
    for it in items:
        loc = it.get("location")
        it["location_fresh"] = fresh_location(it) is not None
        if loc and lat is not None and lng is not None:
            it["distance_km"] = round(haversine_km(lat, lng, loc["lat"], loc["lng"]), 1)
    if lat is not None and lng is not None:
        items.sort(key=lambda x: (not x.get("location_fresh"), x.get("distance_km", 1e9)))
    return items


class LocationBody(BaseModel):
    lat: float
    lng: float
    sharing: bool = True


@api_router.post("/team/location")
async def update_my_location(body: LocationBody, user: dict = Depends(require_role("team", "admin", "super_admin"))):
    loc = {"lat": body.lat, "lng": body.lng, "updated_at": datetime.now(timezone.utc), "sharing": body.sharing}
    await db.users.update_one({"id": user["id"]}, {"$set": {"location": loc}})
    return {"success": True, "location": loc}


@api_router.delete("/team/location")
async def stop_sharing_location(user: dict = Depends(require_role("team", "admin", "super_admin"))):
    await db.users.update_one({"id": user["id"]}, {"$set": {"location.sharing": False, "location.updated_at": None}})
    return {"success": True}


@api_router.post("/team")
async def create_team_member(body: CreateTeamMemberBody, user: dict = Depends(require_role("admin", "super_admin"))):
    existing = await db.users.find_one({"phone": body.phone})
    if existing:
        raise HTTPException(status_code=400, detail="Phone already exists")
    # super_admin can create admin; admin can only create team
    if body.role == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admin can add admins")
    new_user = User(phone=body.phone, name=body.name, role=body.role)
    await db.users.insert_one(new_user.model_dump())
    return new_user.model_dump()


@api_router.delete("/team/{uid}")
async def delete_team(uid: str, user: dict = Depends(require_role("admin", "super_admin"))):
    target = await db.users.find_one({"id": uid}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    if target["role"] == "admin" and user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if target["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot delete super admin")
    await db.users.delete_one({"id": uid})
    return {"success": True}


@api_router.get("/subscribers")
async def list_subscribers(user: dict = Depends(require_role("admin", "super_admin", "team"))):
    items = await db.users.find({"role": "subscriber"}, {"_id": 0}).to_list(1000)
    # attach active subscription
    for it in items:
        sub = await db.subscriptions.find_one({"user_id": it["id"], "status": "active"}, {"_id": 0})
        it["active_plan"] = sub["plan_name"] if sub else None
        it["expires_at"] = sub["expires_at"].isoformat() if sub else None
    return items


@api_router.post("/subscribers")
async def create_subscriber(body: CreateSubscriberBody, user: dict = Depends(require_role("super_admin"))):
    phone = normalize_phone(body.phone)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if await db.users.find_one({"phone": phone}):
        raise HTTPException(status_code=400, detail="Phone already exists")
    plan = None
    if body.plan_id:
        plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
    fields = body.model_dump(exclude={"phone", "name", "plan_id", "payment_mode"})
    new_user = User(phone=phone, name=body.name.strip(), role="subscriber", **fields)
    doc = new_user.model_dump()
    await db.users.insert_one(doc)
    result = clean(doc)
    if plan:
        result["activated"] = await activate_plan(result, plan, body.payment_mode)
    return result


@api_router.patch("/subscribers/{uid}")
async def update_subscriber(uid: str, body: UpdateSubscriberBody, user: dict = Depends(require_role("super_admin"))):
    target = await db.users.find_one({"id": uid, "role": "subscriber"}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "name" in updates and not updates["name"].strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if updates:
        await db.users.update_one({"id": uid}, {"$set": updates})
    return clean(await db.users.find_one({"id": uid}, {"_id": 0}))


@api_router.post("/subscribers/{uid}/assign-plan")
async def assign_plan(uid: str, body: AssignPlanBody, user: dict = Depends(require_role("super_admin"))):
    target = await db.users.find_one({"id": uid, "role": "subscriber"}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return await activate_plan(target, plan, body.payment_mode)


@api_router.delete("/subscribers/{uid}")
async def delete_subscriber(uid: str, user: dict = Depends(require_role("super_admin"))):
    target = await db.users.find_one({"id": uid, "role": "subscriber"}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    await db.users.delete_one({"id": uid})
    await db.subscriptions.delete_many({"user_id": uid})
    await db.complaints.delete_many({"user_id": uid})
    return {"success": True}


# ---------------------- Admin metrics ----------------------
@api_router.get("/admin/metrics")
async def admin_metrics(user: dict = Depends(require_role("admin", "super_admin"))):
    sub_count = await db.users.count_documents({"role": "subscriber"})
    team_count = await db.users.count_documents({"role": "team"})
    active_subs = await db.subscriptions.count_documents({"status": "active"})
    open_complaints = await db.complaints.count_documents({"status": {"$in": ["open", "assigned", "in_progress"]}})
    resolved = await db.complaints.count_documents({"status": "resolved"})
    invoices = await db.invoices.find({"status": "paid"}, {"_id": 0}).to_list(1000)
    revenue = sum(i.get("amount", 0) for i in invoices)
    return {
        "subscribers": sub_count,
        "team_members": team_count,
        "active_subscriptions": active_subs,
        "open_complaints": open_complaints,
        "resolved_complaints": resolved,
        "total_revenue": revenue,
    }


EXPIRY_WINDOW_DAYS = 3


async def expiring_subscriptions(days: int = EXPIRY_WINDOW_DAYS) -> list:
    now = datetime.now(timezone.utc)
    subs = await db.subscriptions.find(
        {"status": "active", "expires_at": {"$lte": now + timedelta(days=days)}}, {"_id": 0}
    ).sort("expires_at", 1).to_list(500)
    if not subs:
        return []
    users = await db.users.find({"id": {"$in": [s["user_id"] for s in subs]}}, {"_id": 0, "id": 1, "name": 1, "phone": 1, "address": 1}).to_list(500)
    umap = {u["id"]: u for u in users}
    out = []
    for s in subs:
        u = umap.get(s["user_id"])
        if not u:
            continue
        out.append({
            "user_id": u["id"], "name": u["name"], "phone": u["phone"], "address": u.get("address"),
            "plan_name": s["plan_name"], "expires_at": s["expires_at"],
            "days_left": max(0, (s["expires_at"] - now).days),
            "expired": s["expires_at"] <= now,
        })
    return out


@api_router.get("/admin/expiring")
async def admin_expiring(days: int = EXPIRY_WINDOW_DAYS, user: dict = Depends(require_role("admin", "super_admin"))):
    return await expiring_subscriptions(days)


@api_router.get("/badges")
async def badges(user: dict = Depends(get_current_user)):
    role = user["role"]
    if role == "team":
        new_tickets = await db.complaints.count_documents({"$or": [
            {"assigned_to": user["id"], "status": "assigned"},
            {"assigned_to": None, "status": "open"},
        ]})
        return {"new_tickets": new_tickets}
    if role in ("admin", "super_admin"):
        return {
            "pending_payments": await db.payments.count_documents({"status": "pending"}),
            "open_tickets": await db.complaints.count_documents({"status": "open"}),
            "expiring_soon": len(await expiring_subscriptions()),
        }
    sub = await db.subscriptions.find_one({"user_id": user["id"], "status": "active"}, {"_id": 0})
    now = datetime.now(timezone.utc)
    return {
        "expiring_soon": bool(sub and sub["expires_at"] <= now + timedelta(days=EXPIRY_WINDOW_DAYS)),
        "days_left": max(0, (sub["expires_at"] - now).days) if sub else None,
    }


@api_router.delete("/auth/me")
async def delete_my_account(user: dict = Depends(get_current_user)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin account cannot be deleted from the app")
    uid = user["id"]
    await db.subscriptions.delete_many({"user_id": uid})
    await db.payments.delete_many({"user_id": uid, "status": "pending"})
    await db.chat_messages.delete_many({"user_id": uid})
    # keep invoices/complaints for records, but anonymise personal data
    anon = {"user_name": "Deleted User", "user_phone": "deleted"}
    await db.invoices.update_many({"user_id": uid}, {"$set": anon})
    await db.complaints.update_many({"user_id": uid}, {"$set": anon})
    await db.payments.update_many({"user_id": uid}, {"$set": anon})
    await db.complaints.update_many({"assigned_to": uid}, {"$set": {"assigned_to": None, "assigned_to_name": None, "status": "open"}})
    await db.users.delete_one({"id": uid})
    return {"success": True}


@api_router.get("/admin/report")
async def collection_report(month: Optional[str] = None, user: dict = Depends(require_role("super_admin"))):
    """Monthly collection report. month = YYYY-MM (defaults to current month, IST)."""
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    try:
        y, m = (int(x) for x in (month or now_ist.strftime("%Y-%m")).split("-"))
        start = datetime(y, m, 1, tzinfo=ist)
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    end = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=ist)
    invoices = await db.invoices.find({"status": "paid", "paid_at": {"$gte": start, "$lt": end}}, {"_id": 0}).to_list(5000)
    by_mode = {"upi": {"count": 0, "amount": 0.0}, "cash": {"count": 0, "amount": 0.0}, "free": {"count": 0, "amount": 0.0}}
    daily: dict[str, float] = {}
    for inv in invoices:
        mode = inv.get("payment_mode") or "upi"
        by_mode.setdefault(mode, {"count": 0, "amount": 0.0})
        by_mode[mode]["count"] += 1
        by_mode[mode]["amount"] += inv.get("amount", 0)
        day = inv["paid_at"].astimezone(ist).strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + inv.get("amount", 0)
    pending = await db.payments.find({"status": "pending"}, {"_id": 0}).to_list(1000)
    # dues = subscribers whose latest subscription expired and who have no active plan
    active_ids = {s["user_id"] for s in await db.subscriptions.find({"status": "active"}, {"_id": 0, "user_id": 1}).to_list(5000)}
    expired = await db.subscriptions.find({"status": "expired", "user_id": {"$nin": list(active_ids)}}, {"_id": 0}).sort("expires_at", -1).to_list(5000)
    seen: set = set()
    dues = []
    for s in expired:
        if s["user_id"] in seen:
            continue
        seen.add(s["user_id"])
        u = await db.users.find_one({"id": s["user_id"], "role": "subscriber"}, {"_id": 0, "name": 1, "phone": 1})
        plan = await db.plans.find_one({"id": s["plan_id"]}, {"_id": 0, "price": 1})
        if u:
            dues.append({"user_id": s["user_id"], "name": u["name"], "phone": u["phone"], "plan_name": s["plan_name"], "expired_at": s["expires_at"], "amount": plan["price"] if plan else 0})
    return {
        "month": f"{y:04d}-{m:02d}",
        "total_collected": sum(v["amount"] for v in by_mode.values()),
        "invoices_count": len(invoices),
        "by_mode": by_mode,
        "daily": [{"date": d, "amount": a} for d, a in sorted(daily.items())],
        "pending_verification": {"count": len(pending), "amount": sum(p.get("amount", 0) for p in pending)},
        "dues": {"count": len(dues), "amount": sum(d["amount"] for d in dues), "items": dues[:100]},
        "recent_invoices": sorted(invoices, key=lambda i: i["paid_at"], reverse=True)[:50],
    }


# ---------------------- Expiry SMS reminders (MSG91 Flow) ----------------------
MSG91_EXPIRY_TEMPLATE_ID = os.environ.get("MSG91_EXPIRY_TEMPLATE_ID", "").strip()
EXPIRY_SMS_ENABLED = bool(MSG91_AUTH_KEY and MSG91_EXPIRY_TEMPLATE_ID)
REMINDER_INTERVAL_SEC = 60 * 60


async def msg91_send_expiry_sms(phone: str, name: str, plan: str, days: int, expires: str) -> None:
    payload = {
        "template_id": MSG91_EXPIRY_TEMPLATE_ID,
        "short_url": "0",
        "recipients": [{"mobiles": f"91{phone}", "name": name, "plan": plan, "days": str(days), "date": expires, "helpline": "8826004211"}],
    }
    async with httpx.AsyncClient(timeout=10) as http:
        r = await http.post("https://control.msg91.com/api/v5/flow", json=payload, headers={"authkey": MSG91_AUTH_KEY, "Content-Type": "application/json", "Accept": "application/json"})
    data = r.json()
    if r.status_code >= 400 or str(data.get("type", "")).lower() == "error":
        raise RuntimeError(f"MSG91 flow rejected: {data}")


async def run_expiry_reminders() -> dict:
    """Send one reminder per subscription when it enters the 3-day expiry window."""
    now = datetime.now(timezone.utc)
    subs = await db.subscriptions.find({
        "status": "active",
        "expires_at": {"$lte": now + timedelta(days=EXPIRY_WINDOW_DAYS), "$gt": now},
        "reminder_sent_at": {"$exists": False},
    }, {"_id": 0}).to_list(500)
    sent = skipped = failed = 0
    for s in subs:
        u = await db.users.find_one({"id": s["user_id"]}, {"_id": 0, "name": 1, "phone": 1})
        if not u:
            continue
        days = max(0, (s["expires_at"] - now).days)
        log = {
            "id": str(uuid.uuid4()), "subscription_id": s["id"], "user_id": s["user_id"], "name": u["name"], "phone": u["phone"],
            "plan_name": s["plan_name"], "expires_at": s["expires_at"], "days_left": days, "created_at": now, "channel": "sms",
        }
        if not EXPIRY_SMS_ENABLED or u["phone"] in DEMO_NUMBERS:
            log["status"] = "skipped"
            log["detail"] = "MSG91 expiry template not configured" if not EXPIRY_SMS_ENABLED else "demo number"
            skipped += 1
        else:
            try:
                await msg91_send_expiry_sms(u["phone"], u["name"], s["plan_name"], days, s["expires_at"].astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y"))
                log["status"] = "sent"
                sent += 1
            except Exception as e:
                logger.error(f"Expiry SMS failed for {u['phone']}: {e}")
                log["status"] = "failed"
                log["detail"] = str(e)[:200]
                failed += 1
        await db.reminders.insert_one(log)
        if log["status"] != "failed":
            await db.subscriptions.update_one({"id": s["id"]}, {"$set": {"reminder_sent_at": now, "reminder_status": log["status"]}})
    return {"checked": len(subs), "sent": sent, "skipped": skipped, "failed": failed, "sms_enabled": EXPIRY_SMS_ENABLED}


async def reminder_loop():
    while True:
        try:
            res = await run_expiry_reminders()
            if res["checked"]:
                logger.info(f"Expiry reminders: {res}")
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
        await asyncio.sleep(REMINDER_INTERVAL_SEC)


@api_router.get("/admin/reminders")
async def list_reminders(user: dict = Depends(require_role("admin", "super_admin"))):
    items = await db.reminders.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"sms_enabled": EXPIRY_SMS_ENABLED, "items": items}


@api_router.post("/admin/reminders/run")
async def run_reminders_now(user: dict = Depends(require_role("super_admin"))):
    return await run_expiry_reminders()


# ---------------------- Chat (Hindi AI Bot) ----------------------
SYSTEM_PROMPT = (
    "You are 'Broadband Solutions 24x7' का हिंदी सहायक (Hindi customer support assistant). "
    "आप एक इंटरनेट सेवा प्रदाता (ISP) के लिए काम करते हैं। "
    "हमेशा हिंदी में उत्तर दें (Devanagari script). Answers should be short, friendly, and helpful. "
    "Topics you handle: broadband plans, recharge, data usage, slow internet, router issues, "
    "how to register a complaint, billing/invoice questions, plan upgrade, wifi password reset. "
    "If asked something unrelated to ISP/broadband, politely redirect. "
    "Keep replies under 4 sentences unless asked for details."
)


@api_router.post("/chat")
async def chat(body: ChatBody, user: dict = Depends(get_current_user)):
    # Save user msg
    umsg = ChatMessage(user_id=user["id"], role="user", text=body.message)
    await db.chat_messages.insert_one(umsg.model_dump())

    reply_text = ""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat_client = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"chat-{user['id']}",
            system_message=SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-haiku-4-5-20251001")
        result = await chat_client.send_message(UserMessage(text=body.message))
        reply_text = str(result) if result else "क्षमा करें, कुछ त्रुटि हुई। कृपया पुनः प्रयास करें।"
    except Exception as e:
        logger.exception("LLM error")
        reply_text = f"क्षमा करें, अभी सहायक उपलब्ध नहीं है। कृपया बाद में पुनः प्रयास करें।"

    amsg = ChatMessage(user_id=user["id"], role="assistant", text=reply_text)
    await db.chat_messages.insert_one(amsg.model_dump())
    return {"reply": reply_text}


@api_router.get("/chat/history")
async def chat_history(user: dict = Depends(get_current_user)):
    items = await db.chat_messages.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return items


@api_router.delete("/chat/history")
async def clear_chat_history(user: dict = Depends(get_current_user)):
    await db.chat_messages.delete_many({"user_id": user["id"]})
    return {"success": True}


# ---------------------- Seed ----------------------
async def seed():
    if await db.users.count_documents({}) > 0:
        return
    logger.info("Seeding initial data...")
    seeds = [
        User(phone="9999999999", name="Super Admin", role="super_admin"),
        User(phone="9999999998", name="Admin Kumar", role="admin"),
        User(phone="9999999997", name="Ravi (Team)", role="team"),
        User(phone="9999999996", name="Amit Sharma", role="subscriber", address="MG Road, Delhi"),
    ]
    await db.users.insert_many([u.model_dump() for u in seeds])

    plans = [
        Plan(name="Basic 50", speed_mbps=50, data_gb=200, validity_days=30, price=499.0,
             description="Perfect for browsing & streaming"),
        Plan(name="Family 100", speed_mbps=100, data_gb=500, validity_days=30, price=799.0,
             description="Great for families & HD streaming"),
        Plan(name="Premium 200", speed_mbps=200, data_gb=1000, validity_days=30, price=1199.0,
             description="Heavy usage, 4K streaming, WFH"),
        Plan(name="Unlimited Pro", speed_mbps=300, data_gb=0, validity_days=30, price=1599.0,
             description="Truly unlimited data, top speed"),
    ]
    await db.plans.insert_many([p.model_dump() for p in plans])
    logger.info("Seed complete")


@app.on_event("startup")
async def startup():
    await seed()
    asyncio.create_task(reminder_loop())
    try:
        await run_in_threadpool(init_storage)
        logger.info("Object storage initialised")
    except Exception as e:
        logger.warning(f"Object storage init failed (will retry on first upload): {e}")


from payment_activity import register_payment_activity

register_payment_activity(api_router, db, get_current_user)
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
