"""
PayFlow Sentinel — Invoices Routes
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
import json, os, uuid
from datetime import datetime
from models.schemas import Invoice, InvoiceCreate, InvoiceStatus

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "invoices.json")


def _load():
    if not os.path.exists(DB_PATH):
        return []
    with open(DB_PATH) as f:
        return json.load(f)

def _save(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


@router.get("/", response_model=List[dict])
def list_invoices(status: Optional[str] = None, po_id: Optional[str] = None):
    invoices = _load()
    if status:
        invoices = [i for i in invoices if i.get("status") == status]
    if po_id:
        invoices = [i for i in invoices if i.get("po_id") == po_id]
    return invoices


@router.get("/{invoice_id}", response_model=dict)
def get_invoice(invoice_id: str):
    invoices = _load()
    match = next((i for i in invoices if i["id"] == invoice_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return match


@router.post("/", response_model=dict, status_code=201)
def submit_invoice(invoice: InvoiceCreate):
    """Vendor submits invoice — triggers InvoiceGuard agent in Maestro."""
    invoices = _load()

    # Check for duplicate invoice number
    duplicate = next((i for i in invoices if i.get("invoice_number") == invoice.invoice_number
                      and i.get("vendor_id") == invoice.vendor_id), None)
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate invoice number {invoice.invoice_number} from vendor {invoice.vendor_id}"
        )

    new_invoice = {
        "id": f"INV-{uuid.uuid4().hex[:8].upper()}",
        "status": InvoiceStatus.RECEIVED,
        "received_at": datetime.utcnow().isoformat(),
        "processed_by_agent": False,
        "risk_score": None,
        "risk_reasons": None,
        "match_result": None,
        "match_delta_pct": None,
        **invoice.dict()
    }
    invoices.append(new_invoice)
    _save(invoices)
    return new_invoice


@router.patch("/{invoice_id}/guard-result")
def update_guard_result(
    invoice_id: str,
    risk_score: float,
    match_result: str,
    match_delta_pct: float,
    risk_reasons: List[str],
    recommendation: str
):
    """InvoiceGuard agent posts its result back to ERP."""
    invoices = _load()
    for inv in invoices:
        if inv["id"] == invoice_id:
            inv["risk_score"] = risk_score
            inv["match_result"] = match_result
            inv["match_delta_pct"] = match_delta_pct
            inv["risk_reasons"] = risk_reasons
            inv["processed_by_agent"] = True
            inv["status"] = (
                InvoiceStatus.MATCHED if match_result == "matched" and risk_score < 40
                else InvoiceStatus.EXCEPTION
            )
            inv["agent_recommendation"] = recommendation
            inv["processed_at"] = datetime.utcnow().isoformat()
            _save(invoices)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")


@router.patch("/{invoice_id}/approve")
def approve_invoice(invoice_id: str, approved_by: str):
    invoices = _load()
    for inv in invoices:
        if inv["id"] == invoice_id:
            inv["status"] = InvoiceStatus.APPROVED
            inv["approved_by"] = approved_by
            inv["approved_at"] = datetime.utcnow().isoformat()
            _save(invoices)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")
