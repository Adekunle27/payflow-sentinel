"""
PayFlow Sentinel — Purchase Orders Routes
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
import json, os, uuid
from datetime import datetime, timedelta
from models.schemas import PurchaseOrder, PurchaseOrderCreate, POStatus

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "purchase_orders.json")


def _load():
    if not os.path.exists(DB_PATH):
        return []
    with open(DB_PATH) as f:
        return json.load(f)

def _save(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


@router.get("/", response_model=List[dict])
def list_pos(status: Optional[str] = None):
    pos = _load()
    if status:
        pos = [p for p in pos if p.get("status") == status]
    return pos


@router.get("/{po_id}", response_model=dict)
def get_po(po_id: str):
    pos = _load()
    match = next((p for p in pos if p["id"] == po_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Purchase Order not found")
    return match


@router.post("/", response_model=dict, status_code=201)
def create_po(po: PurchaseOrderCreate):
    """RPA bot calls this endpoint to create a PO after human approval."""
    pos = _load()
    po_number = f"PO-{datetime.utcnow().strftime('%Y%m')}-{len(pos)+1:04d}"
    new_po = {
        "id": f"PO-{uuid.uuid4().hex[:8].upper()}",
        "po_number": po_number,
        "status": POStatus.APPROVED,
        "created_at": datetime.utcnow().isoformat(),
        "approved_by": None,
        "approved_at": None,
        "delivery_date": (datetime.utcnow() + timedelta(days=14)).isoformat(),
        **po.dict()
    }
    pos.append(new_po)
    _save(pos)
    return new_po


@router.patch("/{po_id}/status")
def update_po_status(po_id: str, status: str, approved_by: Optional[str] = None):
    pos = _load()
    for p in pos:
        if p["id"] == po_id:
            p["status"] = status
            if approved_by:
                p["approved_by"] = approved_by
                p["approved_at"] = datetime.utcnow().isoformat()
            _save(pos)
            return p
    raise HTTPException(status_code=404, detail="PO not found")


@router.post("/{po_id}/goods-receipt")
def record_goods_receipt(po_id: str, received_by: str, notes: Optional[str] = None):
    """Mark goods as received — creates GRN entry, updates PO status."""
    pos = _load()
    for p in pos:
        if p["id"] == po_id:
            p["status"] = POStatus.GOODS_RECEIVED
            p["grn"] = {
                "received_by": received_by,
                "received_at": datetime.utcnow().isoformat(),
                "notes": notes,
                "line_items": p["line_items"],    # Assume full delivery for demo
                "total_value_ngn": p["total_value_ngn"]
            }
            _save(pos)
            return {"po_id": po_id, "grn": p["grn"]}
    raise HTTPException(status_code=404, detail="PO not found")
