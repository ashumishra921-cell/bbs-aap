"""Broadband Solutions 24x7 - Backend"""
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import logging
import uuid
import jwt
import httpx
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
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
@api_router.get("/plans")
async def list_plans():
    plans = await db.plans.find({}, {"_id": 0}).to_list(500)
    return plans


@api_router.post("/plans")
async def create_plan(body: CreatePlanBody, user: dict = Depends(require_role("admin", "super_admin"))):
    plan = Plan(**body.model_dump())
    await db.plans.insert_one(plan.model_dump())
    return plan.model_dump()


@api_router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, user: dict = Depends(require_role("admin", "super_admin"))):
    await db.plans.delete_one({"id": plan_id})
    return {"success": True}


# ---------------------- Recharge / Subscription ----------------------
@api_router.get("/me/subscription")
async def my_subscription(user: dict = Depends(get_current_user)):
    sub = await db.subscriptions.find_one({"user_id": user["id"], "status": "active"}, {"_id": 0}, sort=[("expires_at", -1)])
    return sub


@api_router.post("/recharge")
async def recharge(body: RechargeBody, user: dict = Depends(get_current_user)):
    plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    now = datetime.now(timezone.utc)
    invoice_no = f"INV-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    invoice = Invoice(
        invoice_no=invoice_no,
        user_id=user["id"],
        user_name=user["name"],
        user_phone=user["phone"],
        plan_id=plan["id"],
        plan_name=plan["name"],
        amount=plan["price"],
        upi_id=body.upi_id,
        status="paid",
        paid_at=now,
    )
    await db.invoices.insert_one(invoice.model_dump())

    # Expire old active subs
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
    await db.complaints.insert_one(c.model_dump())
    return c.model_dump()


@api_router.get("/complaints")
async def list_complaints(user: dict = Depends(get_current_user)):
    role = user["role"]
    if role == "subscriber":
        q = {"user_id": user["id"]}
    elif role == "team":
        q = {"assigned_to": user["id"]}
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
        if role not in ("admin", "super_admin"):
            raise HTTPException(status_code=403, detail="Only admin can assign")
        member = await db.users.find_one({"id": body.assigned_to}, {"_id": 0})
        if not member or member["role"] != "team":
            raise HTTPException(status_code=400, detail="Invalid team member")
        updates["assigned_to"] = member["id"]
        updates["assigned_to_name"] = member["name"]
        if not body.status:
            updates["status"] = "assigned"
    if body.status is not None:
        if role == "subscriber":
            raise HTTPException(status_code=403, detail="Forbidden")
        if role == "team" and c.get("assigned_to") != user["id"]:
            raise HTTPException(status_code=403, detail="Not your ticket")
        updates["status"] = body.status
    if body.resolution_note is not None:
        updates["resolution_note"] = body.resolution_note
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.complaints.update_one({"id": cid}, {"$set": updates})
    return clean(await db.complaints.find_one({"id": cid}, {"_id": 0}))


# ---------------------- Team / Users management ----------------------
@api_router.get("/team")
async def list_team(user: dict = Depends(require_role("admin", "super_admin"))):
    items = await db.users.find({"role": {"$in": ["team", "admin"]}}, {"_id": 0}).to_list(500)
    return items


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
    new_user = User(phone=phone, name=body.name.strip(), role="subscriber", address=body.address)
    await db.users.insert_one(new_user.model_dump())
    return new_user.model_dump()


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
