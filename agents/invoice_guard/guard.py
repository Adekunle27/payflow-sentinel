"""
PayFlow Sentinel — Agent 3: InvoiceGuard
★ Built using Claude Code via UiPath for Coding Agents ★

Performs 3-way match (PO / GRN / Invoice), forex validation,
and LLM-based fake invoice detection. Scores invoices 0-100 risk
and recommends: auto_pay | escalate | reject.
"""

import os
import json
import httpx
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from three_way_match import perform_three_way_match
from forex_checker import validate_forex
from fake_detector import detect_fake_invoice

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


# ─── Main Guard Function ──────────────────────────────────────────

def guard_invoice(invoice_id: str) -> dict:
    """
    Full InvoiceGuard pipeline for a submitted invoice.
    Called by UiPath Maestro BPMN after GRN is recorded.
    """
    print(f"\n[InvoiceGuard] ★ Starting analysis for invoice: {invoice_id}")

    # 1. Fetch invoice from ERP
    inv_resp = httpx.get(f"{ERP_BASE_URL}/invoices/{invoice_id}", timeout=10)
    if inv_resp.status_code != 200:
        raise ValueError(f"Invoice {invoice_id} not found in ERP")
    invoice = inv_resp.json()

    # 2. Fetch matching PO
    po_resp = httpx.get(f"{ERP_BASE_URL}/purchase-orders/{invoice['po_id']}", timeout=10)
    if po_resp.status_code != 200:
        raise ValueError(f"PO {invoice['po_id']} not found")
    po = po_resp.json()

    # Get GRN from PO
    grn = po.get("grn")
    if not grn:
        print(f"[InvoiceGuard] ⚠ No GRN found for PO {po['id']} — using PO as GRN proxy")
        grn = {"line_items": po["line_items"], "total_value_ngn": po["total_value_ngn"]}

    print(f"[InvoiceGuard] Invoice: ₦{invoice['total_value_ngn']:,.0f} | PO: ₦{po['total_value_ngn']:,.0f}")

    # ── Step 1: 3-Way Match ───────────────────────────────────────
    match_result = perform_three_way_match(
        po_line_items=po["line_items"],
        grn_line_items=grn["line_items"],
        invoice_line_items=invoice["line_items"],
        po_total=po["total_value_ngn"],
        grn_total=grn["total_value_ngn"],
        invoice_total=invoice["total_value_ngn"],
    )
    print(f"[InvoiceGuard] 3-way match: {match_result['status']} | Delta: {match_result['delta_pct']:.2f}%")

    # ── Step 2: Forex Validation ──────────────────────────────────
    forex_result = validate_forex(
        currency=invoice.get("currency", "NGN"),
        claimed_rate=invoice.get("fx_rate_claimed"),
        invoice_total_ngn=invoice["total_value_ngn"],
        invoice_line_items=invoice["line_items"],
    )
    print(f"[InvoiceGuard] Forex: {'✓ Valid' if forex_result['is_valid'] else '✗ MISMATCH'}")

    # ── Step 3: Fake Invoice Detection ───────────────────────────
    fake_result = detect_fake_invoice(
        invoice=invoice,
        po=po,
        match_result=match_result,
        forex_result=forex_result,
    )
    print(f"[InvoiceGuard] Fraud signals: {len(fake_result['signals'])} | Base risk: {fake_result['base_risk_score']:.0f}")

    # ── Composite Risk Score ──────────────────────────────────────
    risk_score = _compute_composite_risk(match_result, forex_result, fake_result)

    # ── Recommendation ────────────────────────────────────────────
    recommendation = _make_recommendation(risk_score, match_result, forex_result, fake_result)

    # ── Compile all fraud signals ─────────────────────────────────
    all_signals = []
    if match_result["status"] == "exception":
        all_signals.append(f"Price delta {match_result['delta_pct']:.1f}% exceeds 2% threshold")
    if not forex_result["is_valid"] and forex_result.get("rate_deviation_pct"):
        all_signals.append(f"FX rate deviation: {forex_result['rate_deviation_pct']:.1f}%")
    all_signals.extend(fake_result["signals"])

    # ── Build final result ────────────────────────────────────────
    guard_result = {
        "invoice_id": invoice_id,
        "risk_score": round(risk_score, 1),
        "match_status": match_result["status"],
        "po_match": match_result["po_match"],
        "grn_match": match_result["grn_match"],
        "price_delta_pct": round(match_result["delta_pct"], 2),
        "forex_valid": forex_result["is_valid"],
        "forex_claimed_rate": forex_result.get("claimed_rate"),
        "forex_actual_rate": forex_result.get("actual_rate"),
        "forex_deviation_pct": forex_result.get("rate_deviation_pct"),
        "fraud_signals": all_signals,
        "recommendation": recommendation,
        "reasoning": _build_reasoning(risk_score, match_result, forex_result, fake_result, recommendation),
        "analyzed_at": datetime.utcnow().isoformat(),
        "agent": "InvoiceGuard-ClaudeCode-v1",
        "details": {
            "three_way_match": match_result,
            "forex_check": forex_result,
            "fake_detection": fake_result,
        }
    }

    # ── Post result back to ERP ───────────────────────────────────
    httpx.patch(
        f"{ERP_BASE_URL}/invoices/{invoice_id}/guard-result",
        params={
            "risk_score": risk_score,
            "match_result": match_result["status"],
            "match_delta_pct": match_result["delta_pct"],
            "recommendation": recommendation,
        },
        json=all_signals,
        timeout=10,
    )

    print(f"[InvoiceGuard] ★ DONE. Risk: {risk_score:.0f}/100 | Action: {recommendation.upper()}")
    return guard_result


def _compute_composite_risk(match_result, forex_result, fake_result) -> float:
    """Weighted composite risk score."""
    score = 0.0

    # 3-way match weight: 40%
    if match_result["status"] == "exception":
        delta = abs(match_result["delta_pct"])
        match_risk = min(100, delta * 5)   # 20% delta = 100 risk
        score += match_risk * 0.40
    # else 0 risk from match

    # Forex weight: 25%
    if not forex_result["is_valid"]:
        dev = abs(forex_result.get("rate_deviation_pct", 0))
        forex_risk = min(100, dev * 3)
        score += forex_risk * 0.25

    # Fake detection weight: 35%
    score += fake_result["base_risk_score"] * 0.35

    return min(100.0, score)


def _make_recommendation(risk_score, match_result, forex_result, fake_result) -> str:
    if risk_score >= 60:
        return "reject"
    elif risk_score >= 25 or match_result["status"] == "exception" or not forex_result["is_valid"]:
        return "escalate"
    else:
        return "auto_pay"


def _build_reasoning(risk_score, match_result, forex_result, fake_result, recommendation) -> str:
    parts = []

    if match_result["status"] == "matched":
        parts.append(f"3-way match passed with {match_result['delta_pct']:.1f}% variance (within 2% threshold).")
    else:
        parts.append(f"3-way match FAILED: {match_result['delta_pct']:.1f}% price delta detected between PO and invoice.")

    if forex_result["is_valid"]:
        parts.append("Forex rate validated successfully.")
    elif forex_result.get("currency") == "NGN":
        parts.append("Invoice is NGN-denominated — no forex check required.")
    else:
        parts.append(f"Forex MISMATCH: vendor claimed ₦{forex_result.get('claimed_rate',0):,.0f}/USD but actual rate is ₦{forex_result.get('actual_rate',0):,.0f}/USD.")

    signal_count = len(fake_result["signals"])
    if signal_count == 0:
        parts.append("No fraud signals detected.")
    else:
        parts.append(f"{signal_count} fraud signal(s) detected: {', '.join(fake_result['signals'][:2])}.")

    action_map = {
        "auto_pay": "Recommend AUTO-PAY — invoice is clean.",
        "escalate": "Recommend ESCALATE to AP team for human review.",
        "reject": "Recommend REJECT — high fraud risk.",
    }
    parts.append(action_map[recommendation])

    return " ".join(parts)


# ─── FastAPI wrapper ──────────────────────────────────────────────

app = FastAPI(title="InvoiceGuard Agent API — Built with Claude Code ★")

class GuardRequest(BaseModel):
    invoice_id: str

@app.post("/guard")
def guard_endpoint(req: GuardRequest):
    try:
        result = guard_invoice(req.invoice_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "agent": "InvoiceGuard-ClaudeCode-v1", "built_with": "Claude Code via UiPath for Coding Agents"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
