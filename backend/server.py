"""Broadband Solutions 24x7 - Backend"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Request, UploadFile, File
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
import hashlib
import secrets
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url, tz_aware=True)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get('JWT_SECRET', '').strip()
if len(JWT_SECRET) < 32:
    raise RuntimeError('JWT_SECRET must be a securely generated value of at least 32 characters')
JWT_TTL_MINUTES = max(15, int(os.environ.get('JWT_TTL_MINUTES', '480')))
APP_ENV = os.environ.get('APP_ENV', 'production').strip().lower()
ALLOW_DEMO_OTP = APP_ENV == 'development' and os.environ.get('ALLOW_DEMO_OTP', '').strip().lower() == 'true'
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
MOCK_OTP = os.environ.get('DEMO_OTP', '123456')
DEMO_NUMBERS = {p.strip() for p in os.environ.get('DEMO_NUMBERS', '9999999996,9999999997,9999999998,9999999999').split(',') if p.strip()}
MSG91_AUTH_KEY = os.environ.get('MSG91_AUTH_KEY', '').strip()
MSG91_TEMPLATE_ID = os.environ.get('MSG91_TEMPLATE_ID', '').strip()
MSG91_DLT_TE_ID = os.environ.get('MSG91_DLT_TE_ID', '').strip()
TRACCAR_SMS_URL = os.environ.get('TRACCAR_SMS_URL', '').strip().rstrip('/')
TRACCAR_SMS_API_KEY = os.environ.get('TRACCAR_SMS_API_KEY', '').strip()
TRACCAR_SMS_SIM_SLOT_RAW = os.environ.get('TRACCAR_SMS_SIM_SLOT', '').strip()
TRACCAR_SMS_SIM_SLOT = int(TRACCAR_SMS_SIM_SLOT_RAW) if TRACCAR_SMS_SIM_SLOT_RAW in ('0', '1') else None
TRACCAR_SMS_ENABLED = bool(TRACCAR_SMS_URL and TRACCAR_SMS_API_KEY)
MSG91_SMS_ENABLED = bool(MSG91_AUTH_KEY and MSG91_TEMPLATE_ID)
SMS_ENABLED = TRACCAR_SMS_ENABLED or MSG91_SMS_ENABLED
WHATSBOOST_URL = os.environ.get('WHATSBOOST_URL', 'https://whatsboost.in/api/create-message').strip()
WHATSBOOST_APPKEY = os.environ.get('WHATSBOOST_APPKEY', '').strip()
WHATSBOOST_AUTHKEY = os.environ.get('WHATSBOOST_AUTHKEY', '').strip()
WHATSBOOST_NAME = os.environ.get('WHATSBOOST_NAME', 'Broadband Solutions 24x7').strip()
WHATSBOOST_ENABLED = bool(WHATSBOOST_URL and WHATSBOOST_APPKEY and WHATSBOOST_AUTHKEY)
WHATSBOOST_EXPIRY_TEMPLATE_ID = os.environ.get('WHATSBOOST_EXPIRY_TEMPLATE_ID', '').strip()
WHATSBOOST_EXPIRY_TEMPLATE_ENABLED = bool(WHATSBOOST_ENABLED and WHATSBOOST_EXPIRY_TEMPLATE_ID)
OTP_PROVIDER_ENABLED = WHATSBOOST_ENABLED
OTP_RESEND_COOLDOWN_SEC = 30
OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
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
    whatsapp_updates: bool = True
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


class WhatsAppPreferenceBody(BaseModel):
    enabled: bool


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
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_TTL_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def get_token_payload(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub", "jti"]})
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if await db.revoked_tokens.find_one({"jti": payload["jti"]}, {"_id": 0, "jti": 1}):
        raise HTTPException(status_code=401, detail="Session expired")
    return payload


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    payload = await get_token_payload(authorization)
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.get("account_status") == "archived":
        raise HTTPException(status_code=401, detail="Session expired")
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


def uses_mock_otp(phone: str, user: Optional[dict] = None) -> bool:
    """Demo OTP is permitted only in a deliberately configured local development environment."""
    return ALLOW_DEMO_OTP and phone in DEMO_NUMBERS


def client_ip_key(request: Request) -> str:
    raw_ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"{JWT_SECRET}:ip:{raw_ip}".encode()).hexdigest()


async def enforce_auth_limit(action: str, phone: str, request: Request, limit: int, window_minutes: int) -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=window_minutes)
    keys = [(f"{action}:phone", phone), (f"{action}:ip", client_ip_key(request))]
    for bucket, key in keys:
        if await db.auth_throttles.count_documents({"bucket": bucket, "key": key, "created_at": {"$gte": since}}) >= limit:
            raise HTTPException(status_code=429, detail="बहुत अधिक प्रयास हुए हैं। कृपया कुछ देर बाद पुनः प्रयास करें")
    await db.auth_throttles.insert_many([
        {"bucket": bucket, "key": key, "created_at": now, "expires_at": now + timedelta(minutes=window_minutes)}
        for bucket, key in keys
    ])


async def ensure_phone_is_active(phone: str) -> None:
    if await db.retired_phones.find_one({"phone": phone}, {"_id": 0, "phone": 1}):
        raise HTTPException(status_code=403, detail="यह नंबर अब इस खाते के लिए उपयोग नहीं किया जा सकता")


def otp_digest(phone: str, otp: str) -> str:
    return hashlib.sha256(f"{JWT_SECRET}:{phone}:{otp}".encode()).hexdigest()


async def send_traccar_sms(phone: str, message: str) -> None:
    """Send a message through the Android Traccar SMS Gateway local HTTP API."""
    payload = {"to": f"+91{phone}", "message": message}
    if TRACCAR_SMS_SIM_SLOT is not None:
        payload["slot"] = TRACCAR_SMS_SIM_SLOT
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0),
            follow_redirects=False,
            trust_env=False,
        ) as http:
            response = await http.post(
                f"{TRACCAR_SMS_URL}/",
                headers={"Authorization": TRACCAR_SMS_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        logger.error("Traccar SMS gateway timeout: %s", type(exc).__name__)
        raise HTTPException(status_code=504, detail="SMS Gateway का जवाब देर से आ रहा है, कृपया एक बार बाद में प्रयास करें")
    except httpx.HTTPError as exc:
        logger.error("Traccar SMS gateway connection failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="SMS Gateway से कनेक्शन नहीं हो पाया, कृपया बाद में प्रयास करें")
    if not 200 <= response.status_code < 300:
        logger.error("Traccar SMS gateway rejected request: status=%s", response.status_code)
        raise HTTPException(status_code=502, detail="SMS भेजने में समस्या, कृपया बाद में प्रयास करें")
    logger.info("Traccar SMS gateway accepted request: status=%s, phone_suffix=%s, sim_slot=%s", response.status_code, phone[-4:], TRACCAR_SMS_SIM_SLOT)


async def send_transactional_sms(phone: str, message: str) -> bool:
    """Never let an optional notification roll back a completed business action."""
    if not TRACCAR_SMS_ENABLED or phone in DEMO_NUMBERS:
        return False
    try:
        await send_traccar_sms(phone, message)
        return True
    except HTTPException as exc:
        logger.warning("Transactional SMS skipped for %s: %s", phone[-4:], exc.detail)
        return False


async def send_whatsapp_notification(user: dict, event_key: str, message: str) -> bool:
    """Submit one opted-in transactional WhatsApp update; provider success is not delivery proof."""
    if not WHATSBOOST_ENABLED or not user.get("whatsapp_updates", True):
        return False
    now = datetime.now(timezone.utc)
    record = {
        "event_key": event_key,
        "user_id": user["id"],
        "phone_suffix": user["phone"][-4:],
        "category": event_key.split(":", 1)[0],
        "status": "sending",
        "created_at": now,
    }
    try:
        await db.whatsapp_notifications.insert_one(record)
    except DuplicateKeyError:
        return False

    form = {
        "appkey": WHATSBOOST_APPKEY,
        "authkey": WHATSBOOST_AUTHKEY,
        "to": f"91{user['phone']}",
        "name": user["name"][:100],
        "message": message[:3000],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=15.0, write=10.0, pool=10.0), trust_env=False) as http:
            response = await http.post(WHATSBOOST_URL, data=form)
        status = "submitted" if 200 <= response.status_code < 300 else "failed"
        await db.whatsapp_notifications.update_one(
            {"event_key": event_key},
            {"$set": {"status": status, "provider_http": response.status_code, "updated_at": datetime.now(timezone.utc)}},
        )
        if status == "failed":
            logger.warning("WhatsApp notification rejected: event=%s status=%s", record["category"], response.status_code)
        return status == "submitted"
    except httpx.TimeoutException:
        await db.whatsapp_notifications.update_one({"event_key": event_key}, {"$set": {"status": "unknown", "updated_at": datetime.now(timezone.utc)}})
        logger.warning("WhatsApp notification timeout: event=%s", record["category"])
        return False
    except httpx.HTTPError as exc:
        await db.whatsapp_notifications.update_one({"event_key": event_key}, {"$set": {"status": "unknown", "updated_at": datetime.now(timezone.utc)}})
        logger.warning("WhatsApp notification connection failure: %s", type(exc).__name__)
        return False


async def send_whatsboost_otp(phone: str, name: str) -> None:
    """Create a local OTP challenge and send its code only through the configured WhatsBoost gateway."""
    otp = str(secrets.randbelow(900000) + 100000)
    now = datetime.now(timezone.utc)
    await db.otp_challenges.update_one(
        {"phone": phone},
        {"$set": {
            "phone": phone, "otp_hash": otp_digest(phone, otp), "attempts": 0,
            "expires_at": now + timedelta(minutes=OTP_TTL_MINUTES), "created_at": now,
        }},
        upsert=True,
    )
    form = {
        "appkey": WHATSBOOST_APPKEY,
        "authkey": WHATSBOOST_AUTHKEY,
        "to": f"91{phone}",
        "name": name[:100],
        "message": f"Broadband Solutions 24x7: आपका login OTP {otp} है। यह {OTP_TTL_MINUTES} मिनट तक मान्य है। इसे किसी के साथ साझा न करें।",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=20.0, write=10.0, pool=10.0), trust_env=False) as http:
            response = await http.post(WHATSBOOST_URL, data=form)
        if not 200 <= response.status_code < 300:
            raise HTTPException(status_code=502, detail="WhatsApp OTP भेजने में समस्या हुई। कृपया बाद में प्रयास करें")
    except httpx.TimeoutException:
        await db.otp_challenges.delete_one({"phone": phone})
        raise HTTPException(status_code=504, detail="WhatsApp OTP का जवाब देर से आया। कृपया दोबारा प्रयास करें")
    except httpx.HTTPError:
        await db.otp_challenges.delete_one({"phone": phone})
        raise HTTPException(status_code=502, detail="WhatsApp OTP सेवा से कनेक्शन नहीं हो पाया")
    except HTTPException:
        await db.otp_challenges.delete_one({"phone": phone})
        raise


async def send_expiry_template(user: dict, subscription: dict, expiry_date: str, amount: float) -> bool:
    """Send the approved two-day expiry template once for an opted-in subscriber."""
    if not WHATSBOOST_EXPIRY_TEMPLATE_ENABLED or not user.get("whatsapp_updates", True):
        return False
    event_key = f"expiry_template:{subscription['id']}:{subscription['expires_at'].isoformat()}"
    now = datetime.now(timezone.utc)
    try:
        await db.whatsapp_notifications.insert_one({
            "event_key": event_key, "user_id": user["id"], "phone_suffix": user["phone"][-4:],
            "category": "expiry_template", "status": "sending", "created_at": now,
        })
    except DuplicateKeyError:
        return False
    billed_amount = f"₹{amount:,.0f}" if float(amount).is_integer() else f"₹{amount:,.2f}"
    form = {
        "appkey": WHATSBOOST_APPKEY,
        "authkey": WHATSBOOST_AUTHKEY,
        "to": f"91{user['phone']}",
        "name": user["name"][:100],
        "template_id": WHATSBOOST_EXPIRY_TEMPLATE_ID,
        "variables[{1}]": user["name"],
        "variables[{2}]": expiry_date,
        "variables[{3}]": billed_amount,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=8.0, read=15.0, write=10.0, pool=10.0), trust_env=False) as http:
            response = await http.post(WHATSBOOST_URL, data=form)
        status = "submitted" if 200 <= response.status_code < 300 else "failed"
        await db.whatsapp_notifications.update_one(
            {"event_key": event_key},
            {"$set": {"status": status, "provider_http": response.status_code, "updated_at": datetime.now(timezone.utc)}},
        )
        if status == "failed":
            logger.warning("Expiry template rejected: status=%s", response.status_code)
        return status == "submitted"
    except httpx.TimeoutException:
        await db.whatsapp_notifications.update_one({"event_key": event_key}, {"$set": {"status": "unknown", "updated_at": datetime.now(timezone.utc)}})
        logger.warning("Expiry template timeout")
        return False
    except httpx.HTTPError as exc:
        await db.whatsapp_notifications.update_one({"event_key": event_key}, {"$set": {"status": "unknown", "updated_at": datetime.now(timezone.utc)}})
        logger.warning("Expiry template connection failure: %s", type(exc).__name__)
        return False


async def send_traccar_otp(phone: str) -> None:
    otp = str(secrets.randbelow(900000) + 100000)
    now = datetime.now(timezone.utc)
    await db.otp_challenges.update_one(
        {"phone": phone},
        {"$set": {
            "phone": phone, "otp_hash": otp_digest(phone, otp), "attempts": 0,
            "expires_at": now + timedelta(minutes=OTP_TTL_MINUTES), "created_at": now,
        }},
        upsert=True,
    )
    try:
        await send_traccar_sms(phone, f"{otp} is your Broadband Solutions 24x7 OTP. Valid for {OTP_TTL_MINUTES} minutes. Do not share this code.")
    except HTTPException:
        await db.otp_challenges.delete_one({"phone": phone})
        raise


async def verify_local_otp(phone: str, otp: str) -> None:
    challenge = await db.otp_challenges.find_one({"phone": phone}, {"_id": 0})
    now = datetime.now(timezone.utc)
    if not challenge or challenge["expires_at"] <= now:
        await db.otp_challenges.delete_one({"phone": phone})
        raise HTTPException(status_code=400, detail="OTP समाप्त हो गया है। नया OTP मंगाएं")
    if challenge.get("attempts", 0) >= OTP_MAX_ATTEMPTS or challenge["otp_hash"] != otp_digest(phone, otp):
        attempts = challenge.get("attempts", 0) + 1
        if attempts >= OTP_MAX_ATTEMPTS:
            await db.otp_challenges.delete_one({"phone": phone})
        else:
            await db.otp_challenges.update_one({"phone": phone}, {"$set": {"attempts": attempts}})
        raise HTTPException(status_code=400, detail="गलत या समाप्त OTP")
    await db.otp_challenges.delete_one({"phone": phone})


async def notify_plan_activation(user: dict, plan: dict, invoice: Invoice, expires_at: datetime) -> None:
    expiry = expires_at.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y")
    amount = int(invoice.amount) if invoice.amount.is_integer() else invoice.amount
    await send_transactional_sms(
        user["phone"],
        f"Broadband Solutions 24x7: आपका {plan['name']} प्लान सक्रिय हो गया है। वैधता {expiry} तक है। भुगतान ₹{amount} ({invoice.payment_mode.upper()}) प्राप्त हुआ। सहायता: 8826004211",
    )
    await send_whatsapp_notification(
        user,
        f"plan_activation:{invoice.id}",
        f"Broadband Solutions 24x7: आपका {plan['name']} प्लान सक्रिय हो गया है। वैधता {expiry} तक है। भुगतान ₹{amount} प्राप्त हुआ। सहायता: 8826004211",
    )


async def notify_complaint_created(complaint: dict) -> None:
    await send_transactional_sms(
        complaint["user_phone"],
        f"Broadband Solutions 24x7: आपकी शिकायत {complaint['ticket_no']} दर्ज हो गई है। हम जल्द संपर्क करेंगे।",
    )
    subscriber = await db.users.find_one({"id": complaint["user_id"]}, {"_id": 0})
    if subscriber:
        await send_whatsapp_notification(
            subscriber,
            f"complaint_created:{complaint['id']}",
            f"Broadband Solutions 24x7: आपकी शिकायत {complaint['ticket_no']} दर्ज हो गई है। हम जल्द संपर्क करेंगे।",
        )
    if complaint.get("assigned_to"):
        technician = await db.users.find_one({"id": complaint["assigned_to"]}, {"_id": 0, "phone": 1})
        if technician:
            await send_transactional_sms(
                technician["phone"],
                f"नई शिकायत {complaint['ticket_no']}: {complaint['title']}. कृपया ऐप में टिकट देखें।",
            )


async def notify_complaint_update(complaint: dict) -> None:
    label = {"open": "खुली", "assigned": "असाइन", "in_progress": "कार्य जारी", "resolved": "हल"}.get(complaint["status"], complaint["status"])
    await send_transactional_sms(
        complaint["user_phone"],
        f"Broadband Solutions 24x7: शिकायत {complaint['ticket_no']} की स्थिति: {label}।",
    )
    subscriber = await db.users.find_one({"id": complaint["user_id"]}, {"_id": 0})
    if subscriber:
        await send_whatsapp_notification(
            subscriber,
            f"complaint_update:{complaint['id']}:{complaint['status']}:{complaint['updated_at'].isoformat()}",
            f"Broadband Solutions 24x7: शिकायत {complaint['ticket_no']} की स्थिति: {label}।",
        )
    if complaint.get("assigned_to"):
        technician = await db.users.find_one({"id": complaint["assigned_to"]}, {"_id": 0, "phone": 1})
        if technician:
            await send_transactional_sms(
                technician["phone"],
                f"शिकायत {complaint['ticket_no']} अपडेट हुई: {label}. ऐप में विवरण देखें।",
            )


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
    return {"sms_enabled": OTP_PROVIDER_ENABLED, "otp_channel": "whatsapp" if OTP_PROVIDER_ENABLED else None, "demo_otp": None, "resend_cooldown_sec": OTP_RESEND_COOLDOWN_SEC}


@api_router.post("/auth/request-otp")
async def request_otp(body: RequestOtpBody, request: Request):
    phone = normalize_phone(body.phone)
    await ensure_phone_is_active(phone)
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    mock = uses_mock_otp(phone, user)
    await enforce_auth_limit("otp_send", phone, request, limit=5, window_minutes=15)
    if not mock and not OTP_PROVIDER_ENABLED:
        raise HTTPException(status_code=503, detail="WhatsApp OTP सेवा अभी उपलब्ध नहीं है। कृपया बाद में प्रयास करें")
    logger.info(
        "OTP request: phone_suffix=%s role=%s mode=%s provider=%s",
        phone[-4:],
        (user or {}).get("role", "new"),
        "demo" if mock else "whatsapp",
        "whatsboost" if WHATSBOOST_ENABLED else "none",
    )
    now = datetime.now(timezone.utc)
    last = _otp_last_sent.get(phone)
    if last and (now - last).total_seconds() < OTP_RESEND_COOLDOWN_SEC:
        wait = OTP_RESEND_COOLDOWN_SEC - int((now - last).total_seconds())
        raise HTTPException(status_code=429, detail=f"कृपया {wait} सेकंड बाद पुनः प्रयास करें")
    if not mock:
        await send_whatsboost_otp(phone, (user or {}).get("name") or WHATSBOOST_NAME)
    _otp_last_sent[phone] = now
    return {
        "success": True,
        "mode": "demo" if mock else "whatsapp",
        "message": "WhatsApp OTP भेजा गया",
        "otp": None,
        "is_new_user": user is None,
    }


@api_router.post("/auth/verify-otp")
async def verify_otp(body: VerifyOtpBody, request: Request):
    phone = normalize_phone(body.phone)
    await ensure_phone_is_active(phone)
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    mock = uses_mock_otp(phone, user)
    await enforce_auth_limit("otp_verify", phone, request, limit=8, window_minutes=15)
    if not mock and not OTP_PROVIDER_ENABLED:
        raise HTTPException(status_code=503, detail="WhatsApp OTP सेवा अभी उपलब्ध नहीं है। कृपया बाद में प्रयास करें")
    if mock:
        if body.otp != MOCK_OTP:
            raise HTTPException(status_code=400, detail="गलत OTP")
    else:
        await verify_local_otp(phone, body.otp)
    await db.auth_throttles.delete_many({"bucket": {"$in": ["otp_verify:phone", "otp_verify:ip"]}, "key": {"$in": [phone, client_ip_key(request)]}})
    body.phone = phone
    if not user:
        # new subscriber signup
        new_user = User(phone=body.phone, name=body.name or f"User {body.phone[-4:]}", role="subscriber")
        await db.users.insert_one(new_user.model_dump())
        user = new_user.model_dump()
    token = make_token(user["id"])
    return {"token": token, "user": user}


@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {**user, "whatsapp_updates": bool(user.get("whatsapp_updates", True))}


@api_router.get("/me/whatsapp-preference")
async def get_whatsapp_preference(user: dict = Depends(require_role("subscriber"))):
    return {"enabled": bool(user.get("whatsapp_updates", True))}


@api_router.patch("/me/whatsapp-preference")
async def update_whatsapp_preference(body: WhatsAppPreferenceBody, user: dict = Depends(require_role("subscriber"))):
    await db.users.update_one({"id": user["id"]}, {"$set": {"whatsapp_updates": body.enabled, "whatsapp_updates_updated_at": datetime.now(timezone.utc)}})
    return {"enabled": body.enabled}


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    payload = await get_token_payload(authorization)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    await db.revoked_tokens.update_one(
        {"jti": payload["jti"]},
        {"$set": {"jti": payload["jti"], "expires_at": expires_at, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"success": True}


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
    await notify_plan_activation(user, plan, invoice, sub.expires_at)
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
async def get_file(path: str, authorization: Optional[str] = Header(None)):
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
    await send_transactional_sms(
        user["phone"],
        f"Broadband Solutions 24x7: ₹{int(p.amount) if p.amount.is_integer() else p.amount} का भुगतान अनुरोध प्राप्त हुआ है। सत्यापन के बाद आपका प्लान सक्रिय किया जाएगा।",
    )
    await send_whatsapp_notification(
        user,
        f"payment_received:{p.id}",
        f"Broadband Solutions 24x7: ₹{int(p.amount) if p.amount.is_integer() else p.amount} का भुगतान अनुरोध प्राप्त हुआ है। सत्यापन के बाद आपका प्लान सक्रिय किया जाएगा।",
    )
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
    if user["role"] not in ("admin", "super_admin") and inv["user_id"] != user["id"]:
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
    await notify_complaint_created(doc)
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
    updated = clean(await db.complaints.find_one({"id": cid}, {"_id": 0}))
    await notify_complaint_update(updated)
    return updated


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


# ---------------------- Expiry SMS reminders ----------------------
MSG91_EXPIRY_TEMPLATE_ID = os.environ.get("MSG91_EXPIRY_TEMPLATE_ID", "").strip()
EXPIRY_SMS_ENABLED = TRACCAR_SMS_ENABLED or bool(MSG91_AUTH_KEY and MSG91_EXPIRY_TEMPLATE_ID)
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


async def send_expiry_sms(phone: str, name: str, plan: str, days: int, expires: str) -> None:
    if TRACCAR_SMS_ENABLED:
        await send_traccar_sms(
            phone,
            f"Broadband Solutions 24x7: नमस्ते {name}, आपका {plan} प्लान {expires} को समाप्त हो रहा है ({days} दिन बाकी)। समय पर रिचार्ज करें। सहायता: 8826004211",
        )
        return
    await msg91_send_expiry_sms(phone, name, plan, days, expires)


async def run_expiry_reminders() -> dict:
    """Send the approved WhatsBoost template on the calendar date two days before expiry."""
    now = datetime.now(timezone.utc)
    india_tz = timezone(timedelta(hours=5, minutes=30))
    target_expiry_date = now.astimezone(india_tz).date() + timedelta(days=2)
    subs = await db.subscriptions.find({
        "status": "active",
        "expires_at": {"$lte": now + timedelta(days=3), "$gt": now + timedelta(days=1)},
        "whatsapp_expiry_template_sent_at": {"$exists": False},
    }, {"_id": 0}).to_list(500)
    sent = skipped = failed = 0
    for s in subs:
        u = await db.users.find_one({"id": s["user_id"]}, {"_id": 0, "id": 1, "name": 1, "phone": 1, "whatsapp_updates": 1})
        if not u:
            continue
        expiry_date = s["expires_at"].astimezone(india_tz)
        if expiry_date.date() != target_expiry_date:
            continue
        plan = await db.plans.find_one({"id": s["plan_id"]}, {"_id": 0, "price": 1})
        amount = float((plan or {}).get("price", 0))
        log = {
            "id": str(uuid.uuid4()), "subscription_id": s["id"], "user_id": s["user_id"], "name": u["name"], "phone": u["phone"],
            "plan_name": s["plan_name"], "expires_at": s["expires_at"], "days_left": 2, "amount": amount, "created_at": now, "channel": "whatsapp_template",
        }
        try:
            delivered = await send_expiry_template(u, s, expiry_date.strftime("%d %b %Y"), amount)
            if delivered:
                log["status"] = "sent"
                sent += 1
            else:
                log["status"] = "skipped"
                log["detail"] = "No opted-in WhatsApp recipient or expiry template configured"
                skipped += 1
        except Exception as exc:
            logger.error("Expiry template preparation failed: %s", type(exc).__name__)
            log["status"] = "failed"
            failed += 1
        await db.reminders.insert_one(log)
        if log["status"] != "failed":
            await db.subscriptions.update_one({"id": s["id"]}, {"$set": {"whatsapp_expiry_template_sent_at": now, "whatsapp_expiry_template_status": log["status"]}})
    return {"checked": len(subs), "sent": sent, "skipped": skipped, "failed": failed, "whatsapp_template_enabled": WHATSBOOST_EXPIRY_TEMPLATE_ENABLED}


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
    return {"whatsapp_template_enabled": WHATSBOOST_EXPIRY_TEMPLATE_ENABLED, "items": items}


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
    bootstrap_phone = os.environ.get("BOOTSTRAP_SUPER_ADMIN_PHONE", "").strip()
    if bootstrap_phone:
        await db.users.insert_one(User(phone=normalize_phone(bootstrap_phone), name="Super Admin", role="super_admin").model_dump())
    else:
        logger.warning("No BOOTSTRAP_SUPER_ADMIN_PHONE configured; skipping initial privileged-user seed")

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
    await db.auth_throttles.create_index("expires_at", expireAfterSeconds=0)
    await db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.revoked_tokens.create_index("jti", unique=True)
    await db.whatsapp_notifications.create_index("event_key", unique=True)
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
ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), payment=()"
    if request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
