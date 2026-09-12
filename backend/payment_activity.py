"""Read-only, role-scoped payment ledger and foreground activity snapshots."""
import re
from datetime import datetime
from typing import Literal, Optional

from fastapi import Depends, Query
from pydantic import BaseModel


class PaymentHistoryItem(BaseModel):
    id: str
    invoice_id: Optional[str] = None
    user_id: str
    user_name: str
    user_phone: str
    plan_name: str
    amount: float
    payment_mode: str
    status: str
    created_at: datetime
    reject_reason: Optional[str] = None


class PaymentHistoryPage(BaseModel):
    items: list[PaymentHistoryItem]
    has_more: bool


class ActivityItem(BaseModel):
    key: str
    version: str
    kind: Literal["complaint", "payment"]
    title: str


def register_payment_activity(router, db, current_user):
    @router.get("/payment-history", response_model=PaymentHistoryPage)
    async def payment_history(
        mode: Literal["all", "upi", "cash", "free"] = "all",
        search: str = Query("", max_length=100),
        offset: int = Query(0, ge=0),
        limit: int = Query(40, ge=1, le=100),
        user: dict = Depends(current_user),
    ):
        scope = {} if user["role"] in ("admin", "super_admin") else {"user_id": user["id"]}
        fields = {"_id": 0, "user_id": 1, "user_name": 1, "user_phone": 1,
                  "plan_name": 1, "amount": 1, "status": 1, "created_at": 1}
        pipeline = [
            {"$match": scope},
            {"$project": {**fields, "id": {"$concat": ["invoice-", "$id"]},
                          "invoice_id": "$id", "payment_mode": {"$ifNull": ["$payment_mode", "upi"]}}},
            {"$unionWith": {"coll": "payments", "pipeline": [
                {"$match": scope},
                {"$lookup": {"from": "invoices", "localField": "invoice_id", "foreignField": "id", "as": "receipt"}},
                # Approved screenshot + receipt are ONE payment, not two.
                {"$match": {"receipt": {"$size": 0}}},
                {"$project": {**fields, "id": {"$concat": ["payment-", "$id"]},
                              "payment_mode": {"$literal": "upi"}, "reject_reason": 1}},
            ]}},
        ]
        filters = {}
        if mode != "all":
            filters["payment_mode"] = mode
        if search.strip():
            term = {"$regex": re.escape(search.strip()), "$options": "i"}
            filters["$or"] = [{key: term} for key in ("user_name", "user_phone", "plan_name")]
        pipeline += [{"$match": filters}, {"$sort": {"created_at": -1, "id": 1}},
                     {"$skip": offset}, {"$limit": limit + 1}]
        items = await db.invoices.aggregate(pipeline).to_list(limit + 1)
        return PaymentHistoryPage(items=items[:limit], has_more=len(items) > limit)

    @router.get("/activity", response_model=list[ActivityItem])
    async def activity(user: dict = Depends(current_user)):
        role, uid = user["role"], user["id"]
        scope = {} if role in ("admin", "super_admin") else {"user_id": uid}
        complaint_scope = scope
        if role == "team":
            complaint_scope = {"$or": [{"assigned_to": uid}, {"assigned_to": None, "status": "open"}]}
        complaints = await db.complaints.find(complaint_scope, {"_id": 0}).sort("updated_at", -1).to_list(200)
        items = [ActivityItem(
            key=f"complaint-{c['id']}", kind="complaint",
            version=f"{c.get('updated_at', c['created_at'])}:{c['status']}:{c.get('assigned_to')}",
            title=f"Complaint {c['ticket_no']} · {c['status'].replace('_', ' ')}",
        ) for c in complaints]
        if role == "team":
            return items
        payments = await db.payments.find(scope, {"_id": 0}).sort("created_at", -1).to_list(200)
        items += [ActivityItem(
            key=f"payment-{p['id']}", kind="payment", version=p["status"],
            title=f"UPI ₹{p['amount']:g} · {p['user_name']} · {p['status']}",
        ) for p in payments]
        invoices = await db.invoices.find({**scope, "status": "paid"}, {"_id": 0}).sort("created_at", -1).to_list(200)
        items += [ActivityItem(
            key=f"invoice-{i['id']}", kind="payment", version="paid",
            title=f"{i.get('payment_mode', 'upi').upper()} ₹{i['amount']:g} received · {i['user_name']}",
        ) for i in invoices]
        return items