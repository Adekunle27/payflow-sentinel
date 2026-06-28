"""
PayFlow Sentinel — Mock ERP Backend
Railway-compatible entry point.
"""

import sys
import os

# Ensure backend/ is on the path regardless of where Railway runs from
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime

# ── Inline the routes to avoid import path issues on Railway ──

app = FastAPI(
    title="PayFlow Sentinel — Mock ERP API",
    description="Simulated ERP for PayFlow Sentinel P2P orchestration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data directory — works both locally and on Railway ──
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def _load(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)

def _save(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

# ── Health ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "PayFlow Sentinel Mock ERP", "status": "running",
            "timestamp": datetime.utcnow().isoformat()}

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ── Budget Codes ──────────────────────────────────────────────

@app.get("/budget-codes")
def get_budget_codes():
    return _load("budget_codes.json")

@app.get("/budget-codes/{code}/balance")
def get_budget_balance(code: str):
    codes = _load("budget_codes.json")
    match = next((c for c in codes if c["code"] == code), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Budget code {code} not found")
    return {"code": code, "department": match["department"],
            "allocated": match["allocated_ngn"], "spent": match["spent_ngn"],
            "available": match["allocated_ngn"] - match["spent_ngn"]}

# ── Vendors ───────────────────────────────────────────────────

@app.get("/vendors")
def list_vendors(status: str = None, category: str = None):
    vendors = _load("vendors.json")
    if status: vendors = [v for v in vendors if v.get("status") == status]
    if category: vendors = [v for v in vendors if v.get("category") == category]
    return vendors

@app.get("/vendors/search/name")
def search_vendors(q: str):
    vendors = _load("vendors.json")
    q_lower = q.lower()
    return [v for v in vendors if q_lower in v["name"].lower()]

@app.get("/vendors/blacklist/check")
def check_blacklist(name: str = None, cac: str = None):
    blacklist = _load("blacklist.json")
    hits = []
    for entry in blacklist:
        if name and name.lower() in entry.get("name", "").lower(): hits.append(entry)
        elif cac and cac == entry.get("cac_number"): hits.append(entry)
    return {"is_blacklisted": len(hits) > 0, "hits": hits}

@app.get("/vendors/{vendor_id}")
def get_vendor(vendor_id: str):
    vendors = _load("vendors.json")
    match = next((v for v in vendors if v["id"] == vendor_id), None)
    if not match: raise HTTPException(status_code=404, detail="Vendor not found")
    return match

# ── Purchase Orders ───────────────────────────────────────────

@app.get("/purchase-orders")
def list_pos(status: str = None):
    pos = _load("purchase_orders.json")
    if status: pos = [p for p in pos if p.get("status") == status]
    return pos

@app.get("/purchase-orders/{po_id}")
def get_po(po_id: str):
    pos = _load("purchase_orders.json")
    match = next((p for p in pos if p["id"] == po_id), None)
    if not match: raise HTTPException(status_code=404, detail="PO not found")
    return match

@app.post("/purchase-orders", status_code=201)
def create_po(body: dict):
    import uuid
    pos = _load("purchase_orders.json")
    po_number = f"PO-{datetime.utcnow().strftime('%Y%m')}-{len(pos)+1:04d}"
    new_po = {"id": f"PO-{uuid.uuid4().hex[:8].upper()}", "po_number": po_number,
              "status": "approved", "created_at": datetime.utcnow().isoformat(), **body}
    pos.append(new_po)
    _save("purchase_orders.json", pos)
    return new_po

@app.patch("/purchase-orders/{po_id}/status")
def update_po_status(po_id: str, status: str, approved_by: str = None):
    pos = _load("purchase_orders.json")
    for p in pos:
        if p["id"] == po_id:
            p["status"] = status
            if approved_by: p["approved_by"] = approved_by
            _save("purchase_orders.json", pos)
            return p
    raise HTTPException(status_code=404, detail="PO not found")

@app.post("/purchase-orders/{po_id}/goods-receipt")
def record_grn(po_id: str, received_by: str, notes: str = None):
    pos = _load("purchase_orders.json")
    for p in pos:
        if p["id"] == po_id:
            p["status"] = "goods_received"
            p["grn"] = {"received_by": received_by, "received_at": datetime.utcnow().isoformat(),
                        "notes": notes, "line_items": p.get("line_items", []),
                        "total_value_ngn": p.get("total_value_ngn", 0)}
            _save("purchase_orders.json", pos)
            return {"po_id": po_id, "grn": p["grn"]}
    raise HTTPException(status_code=404, detail="PO not found")

# ── Invoices ──────────────────────────────────────────────────

@app.get("/invoices")
def list_invoices(status: str = None, po_id: str = None):
    invoices = _load("invoices.json")
    if status: invoices = [i for i in invoices if i.get("status") == status]
    if po_id: invoices = [i for i in invoices if i.get("po_id") == po_id]
    return invoices

@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str):
    invoices = _load("invoices.json")
    match = next((i for i in invoices if i["id"] == invoice_id), None)
    if not match: raise HTTPException(status_code=404, detail="Invoice not found")
    return match

@app.post("/invoices", status_code=201)
def submit_invoice(body: dict):
    import uuid
    invoices = _load("invoices.json")
    inv_number = body.get("invoice_number")
    vendor_id = body.get("vendor_id")
    duplicate = next((i for i in invoices if i.get("invoice_number") == inv_number
                      and i.get("vendor_id") == vendor_id), None)
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Duplicate invoice number {inv_number}")
    new_inv = {"id": f"INV-{uuid.uuid4().hex[:8].upper()}", "status": "received",
               "received_at": datetime.utcnow().isoformat(), "processed_by_agent": False,
               "risk_score": None, "risk_reasons": None, "match_result": None, **body}
    invoices.append(new_inv)
    _save("invoices.json", invoices)
    return new_inv

@app.patch("/invoices/{invoice_id}/guard-result")
def update_guard_result(invoice_id: str, risk_score: float, match_result: str,
                         match_delta_pct: float, recommendation: str, body: list = None):
    invoices = _load("invoices.json")
    for inv in invoices:
        if inv["id"] == invoice_id:
            inv.update({"risk_score": risk_score, "match_result": match_result,
                        "match_delta_pct": match_delta_pct, "processed_by_agent": True,
                        "agent_recommendation": recommendation,
                        "status": "matched" if match_result == "matched" and risk_score < 40 else "exception",
                        "processed_at": datetime.utcnow().isoformat()})
            _save("invoices.json", invoices)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")

@app.patch("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: str, approved_by: str):
    invoices = _load("invoices.json")
    for inv in invoices:
        if inv["id"] == invoice_id:
            inv.update({"status": "approved", "approved_by": approved_by,
                        "approved_at": datetime.utcnow().isoformat()})
            _save("invoices.json", invoices)
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")

# ── Payments ──────────────────────────────────────────────────

@app.get("/payments")
def list_payments():
    return _load("payments.json")

@app.post("/payments", status_code=201)
def execute_payment(body: dict):
    import uuid
    payments = _load("payments.json")
    ref = f"PAY-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    amount = body.get("amount_ngn", 0)
    new_payment = {
        "id": f"PMT-{uuid.uuid4().hex[:8].upper()}",
        "payment_reference": ref, "status": "completed",
        "executed_at": datetime.utcnow().isoformat(),
        "audit_log": [
            f"Payment initiated at {datetime.utcnow().isoformat()}",
            f"Amount: NGN {amount:,.2f}",
            f"Method: {body.get('payment_method', 'bank_transfer')}",
            f"Approved by: {body.get('approved_by', 'system')}",
            f"Reference: {ref}",
        ],
        **body
    }
    payments.append(new_payment)
    _save("payments.json", payments)
    return new_payment

# ── Process Variables endpoint (for Maestro integration) ──────

@app.post("/process/start")
def start_process(body: dict):
    """Entry point called by Maestro to kick off a P2P process instance."""
    import uuid
    return {
        "process_instance_id": f"INST-{uuid.uuid4().hex[:8].upper()}",
        "status": "started",
        "started_at": datetime.utcnow().isoformat(),
        "input": body,
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
