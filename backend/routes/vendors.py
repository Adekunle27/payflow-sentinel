"""
PayFlow Sentinel — Vendor Registry Routes
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
import json, os, uuid
from datetime import datetime
from models.schemas import Vendor, VendorCreate, VendorStatus

router = APIRouter()
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "vendors.json")
BLACKLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "blacklist.json")


def _load_vendors():
    with open(DB_PATH) as f:
        return json.load(f)

def _save_vendors(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)

def _load_blacklist():
    with open(BLACKLIST_PATH) as f:
        return json.load(f)


@router.get("/", response_model=List[dict])
def list_vendors(status: Optional[str] = None, category: Optional[str] = None):
    vendors = _load_vendors()
    if status:
        vendors = [v for v in vendors if v.get("status") == status]
    if category:
        vendors = [v for v in vendors if v.get("category") == category]
    return vendors


@router.get("/{vendor_id}", response_model=dict)
def get_vendor(vendor_id: str):
    vendors = _load_vendors()
    match = next((v for v in vendors if v["id"] == vendor_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return match


@router.post("/", response_model=dict, status_code=201)
def create_vendor(vendor: VendorCreate):
    vendors = _load_vendors()
    new_vendor = {
        "id": f"VND-{uuid.uuid4().hex[:8].upper()}",
        "status": VendorStatus.ACTIVE,
        "trust_score": 50.0,
        "transaction_count": 0,
        "total_value_ngn": 0.0,
        "registered_at": datetime.utcnow().isoformat(),
        **vendor.dict()
    }
    vendors.append(new_vendor)
    _save_vendors(vendors)
    return new_vendor


@router.get("/search/name")
def search_by_name(q: str):
    """Search vendors by name — used by VendorScout for duplicate detection."""
    vendors = _load_vendors()
    q_lower = q.lower()
    results = [
        v for v in vendors
        if q_lower in v["name"].lower() or
           _similarity_score(q_lower, v["name"].lower()) > 0.7
    ]
    return results


@router.get("/blacklist/check")
def check_blacklist(name: Optional[str] = None, cac: Optional[str] = None):
    """Check if a vendor name or CAC number is blacklisted."""
    blacklist = _load_blacklist()

    hits = []
    for entry in blacklist:
        if name and name.lower() in entry.get("name", "").lower():
            hits.append(entry)
        elif cac and cac == entry.get("cac_number"):
            hits.append(entry)

    return {
        "is_blacklisted": len(hits) > 0,
        "hits": hits,
        "checked_name": name,
        "checked_cac": cac,
    }


@router.patch("/{vendor_id}/trust-score")
def update_trust_score(vendor_id: str, score: float, reason: str = ""):
    vendors = _load_vendors()
    for v in vendors:
        if v["id"] == vendor_id:
            v["trust_score"] = max(0, min(100, score))
            _save_vendors(vendors)
            return {"vendor_id": vendor_id, "new_trust_score": score, "reason": reason}
    raise HTTPException(status_code=404, detail="Vendor not found")


def _similarity_score(a: str, b: str) -> float:
    """Simple character overlap similarity — catches fake vendor names like 'Dangote Supplies Ltd' vs 'Dangote Suppliies Ltd'."""
    if not a or not b:
        return 0.0
    set_a, set_b = set(a.split()), set(b.split())
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0
