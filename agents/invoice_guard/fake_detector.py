"""
PayFlow Sentinel — InvoiceGuard: Fake Invoice Detector
★ Built with Claude Code via UiPath for Coding Agents ★

Uses Claude to analyze invoice patterns and detect fraud signals
common in Nigerian enterprise procurement fraud.
"""

import os
import json
import re
from anthropic import Anthropic
from typing import Dict, List

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = Anthropic(api_key=ANTHROPIC_API_KEY)


FRAUD_DETECTION_PROMPT = """You are an expert forensic accountant specializing in procurement fraud detection in Nigerian enterprises.

Analyze this invoice data and detect fraud signals. You understand these common Nigerian procurement fraud patterns:
1. Round-number fraud: invoice totals that are suspiciously round (e.g. exactly ₦5,000,000)
2. Price inflation: unit prices significantly above market rate
3. Ghost line items: items on invoice not in original PO
4. Duplicate invoice patterns: same amount/description submitted before
5. Vendor impersonation: slight name variations to mimic legitimate vendors
6. Split invoice fraud: breaking one large invoice into multiple smaller ones to avoid approval thresholds
7. Goods substitution: invoicing for premium items, delivering cheaper ones

INVOICE DATA:
{invoice_json}

PURCHASE ORDER DATA:
{po_json}

THREE-WAY MATCH RESULT:
{match_json}

FOREX RESULT:
{forex_json}

Analyze and respond ONLY with this JSON (no other text):
{{
  "signals": ["list of specific fraud signals detected"],
  "base_risk_score": 0,
  "round_number_flag": false,
  "price_inflation_flag": false,
  "ghost_line_items": [],
  "split_invoice_risk": false,
  "analysis_notes": "2-3 sentence expert summary"
}}

base_risk_score: 0-100 based on fraud signals only (not match/forex — those are handled separately)
- 0-20: Clean, no significant signals
- 21-40: Minor concerns
- 41-70: Multiple red flags
- 71-100: Strong fraud indicators
"""


def detect_fake_invoice(
    invoice: Dict,
    po: Dict,
    match_result: Dict,
    forex_result: Dict,
) -> Dict:
    """
    Use Claude to analyze invoice for fraud signals.
    Returns risk score and list of specific fraud signals detected.
    """

    # Prepare sanitized data for Claude (remove noise)
    invoice_clean = {
        "id": invoice.get("id"),
        "invoice_number": invoice.get("invoice_number"),
        "vendor_id": invoice.get("vendor_id"),
        "invoice_date": invoice.get("invoice_date"),
        "total_value_ngn": invoice.get("total_value_ngn"),
        "currency": invoice.get("currency"),
        "line_items": invoice.get("line_items", []),
        "fx_rate_claimed": invoice.get("fx_rate_claimed"),
    }

    po_clean = {
        "id": po.get("id"),
        "po_number": po.get("po_number"),
        "total_value_ngn": po.get("total_value_ngn"),
        "line_items": po.get("line_items", []),
        "created_at": po.get("created_at"),
    }

    match_clean = {
        "status": match_result.get("status"),
        "delta_pct": match_result.get("delta_pct"),
        "line_item_exceptions": match_result.get("line_item_exceptions", []),
    }

    forex_clean = {
        "currency": forex_result.get("currency"),
        "is_valid": forex_result.get("is_valid"),
        "rate_deviation_pct": forex_result.get("rate_deviation_pct"),
    }

    prompt = FRAUD_DETECTION_PROMPT.format(
        invoice_json=json.dumps(invoice_clean, indent=2),
        po_json=json.dumps(po_clean, indent=2),
        match_json=json.dumps(match_clean, indent=2),
        forex_json=json.dumps(forex_clean, indent=2),
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # Parse JSON
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(raw)

        # Also run rule-based checks to supplement LLM
        rule_signals = _rule_based_checks(invoice, po)
        for sig in rule_signals:
            if sig not in result.get("signals", []):
                result.setdefault("signals", []).append(sig)

        # Boost score if rule-based checks fired
        if rule_signals:
            result["base_risk_score"] = min(100, result.get("base_risk_score", 0) + len(rule_signals) * 10)

        result["source"] = "claude-sonnet-4-6 + rule-engine"
        return result

    except Exception as e:
        print(f"[FakeDetector] Claude call failed: {e}. Falling back to rule-based only.")
        rule_signals = _rule_based_checks(invoice, po)
        return {
            "signals": rule_signals,
            "base_risk_score": len(rule_signals) * 15,
            "round_number_flag": _is_round_number(invoice.get("total_value_ngn", 0)),
            "price_inflation_flag": False,
            "ghost_line_items": [],
            "split_invoice_risk": False,
            "analysis_notes": f"Rule-based analysis only (Claude unavailable). {len(rule_signals)} signals found.",
            "source": "rule-engine-fallback",
        }


def _rule_based_checks(invoice: Dict, po: Dict) -> List[str]:
    """Fast rule-based fraud signals that don't require LLM."""
    signals = []

    total = invoice.get("total_value_ngn", 0)

    # Round number check
    if _is_round_number(total):
        signals.append(f"Suspiciously round invoice total: ₦{total:,.0f}")

    # Just-under-threshold check (classic split invoice / avoid approval)
    thresholds = [5_000_000, 10_000_000, 20_000_000, 50_000_000]
    for threshold in thresholds:
        if threshold * 0.95 <= total < threshold:
            signals.append(f"Invoice total ₦{total:,.0f} is suspiciously just under ₦{threshold:,.0f} approval threshold")

    # Date check — invoice dated before PO
    try:
        inv_date = invoice.get("invoice_date", "")
        po_date = po.get("created_at", "")
        if inv_date and po_date and inv_date[:10] < po_date[:10]:
            signals.append(f"Invoice date ({inv_date[:10]}) precedes PO creation date ({po_date[:10]}) — possible backdating")
    except Exception:
        pass

    # Missing invoice number
    if not invoice.get("invoice_number"):
        signals.append("Invoice has no invoice number — high risk indicator")

    # Extremely high line item count vs PO
    inv_lines = len(invoice.get("line_items", []))
    po_lines = len(po.get("line_items", []))
    if inv_lines > po_lines * 1.5 and po_lines > 0:
        signals.append(f"Invoice has {inv_lines} line items vs PO's {po_lines} — possible ghost line items")

    return signals


def _is_round_number(amount: float) -> bool:
    """Detect suspiciously round amounts."""
    if amount <= 0:
        return False
    # Divisible by 500,000 or more
    for divisor in [5_000_000, 2_000_000, 1_000_000, 500_000]:
        if amount >= divisor and amount % divisor == 0:
            return True
    return False
