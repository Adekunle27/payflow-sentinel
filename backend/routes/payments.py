"""
PayFlow Sentinel — Payments Routes
"""

from fastapi import APIRouter, HTTPException
import json, os, uuid
from datetime import datetime
from typing import List
from models.schemas import PaymentCreate

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "payments.json")


def _load():
    if not os.path.exists(DB_PATH):
        return []
    with open(DB_PATH) as f:
        return json.load(f)

def _save(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


@router.get("/", response_model=List[dict])
def list_payments():
    return _load()


@router.post("/", response_model=dict, status_code=201)
def execute_payment(payment: PaymentCreate):
    """RPA bot calls this to log payment execution after AP approval."""
    payments = _load()
    ref = f"PAY-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    new_payment = {
        "id": f"PMT-{uuid.uuid4().hex[:8].upper()}",
        "payment_reference": ref,
        "status": "completed",
        "executed_at": datetime.utcnow().isoformat(),
        "audit_log": [
            f"Payment initiated at {datetime.utcnow().isoformat()}",
            f"Amount: ₦{payment.amount_ngn:,.2f}",
            f"Method: {payment.payment_method}",
            f"Approved by: {payment.approved_by}",
            f"Reference: {ref}",
        ],
        **payment.dict()
    }
    payments.append(new_payment)
    _save(payments)
    return new_payment


@router.get("/{payment_id}")
def get_payment(payment_id: str):
    payments = _load()
    match = next((p for p in payments if p["id"] == payment_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Payment not found")
    return match
