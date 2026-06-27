"""
PayFlow Sentinel — InvoiceGuard: Forex Checker
★ Built with Claude Code via UiPath for Coding Agents ★

Validates FX rates on foreign-currency invoices.
Catches vendors inflating USD/NGN rates to extract more Naira.
"""

import os
import httpx
from datetime import datetime
from typing import Optional, List, Dict


# Fallback rate if API is unavailable (update periodically)
FALLBACK_USD_NGN = 1580.0
FALLBACK_GBP_NGN = 2010.0
FALLBACK_EUR_NGN = 1730.0

FX_TOLERANCE_PCT = 3.0   # Allow 3% variance from official rate (bank spread)
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY", "")


def validate_forex(
    currency: str,
    claimed_rate: Optional[float],
    invoice_total_ngn: float,
    invoice_line_items: List[Dict],
) -> Dict:
    """
    Validate forex rate on a foreign-currency invoice.
    Returns validation result with actual vs claimed rate comparison.
    """

    result = {
        "currency": currency,
        "claimed_rate": claimed_rate,
        "actual_rate": None,
        "rate_deviation_pct": None,
        "is_valid": True,
        "checked_at": datetime.utcnow().isoformat(),
        "source": None,
    }

    # NGN invoices don't need forex check
    if currency == "NGN" or currency is None:
        result["is_valid"] = True
        result["source"] = "no_fx_required"
        return result

    # Get actual market rate
    actual_rate = _fetch_live_rate(currency)
    result["actual_rate"] = actual_rate
    result["source"] = "exchangerate-api.com" if EXCHANGE_RATE_API_KEY else "fallback_rate"

    # If no claimed rate provided, can't validate
    if not claimed_rate:
        result["is_valid"] = True
        result["note"] = "No claimed rate provided — cannot validate FX"
        return result

    # Compare claimed vs actual
    deviation_pct = abs(claimed_rate - actual_rate) / actual_rate * 100
    result["rate_deviation_pct"] = round(deviation_pct, 2)
    result["is_valid"] = deviation_pct <= FX_TOLERANCE_PCT

    if not result["is_valid"]:
        # Calculate how much extra NGN vendor is extracting
        # With correct rate vs their inflated rate
        implied_foreign_amount = invoice_total_ngn / claimed_rate
        correct_ngn_amount = implied_foreign_amount * actual_rate
        overcharge_ngn = invoice_total_ngn - correct_ngn_amount

        result["overcharge_analysis"] = {
            "implied_foreign_amount": round(implied_foreign_amount, 2),
            "correct_ngn_at_actual_rate": round(correct_ngn_amount, 2),
            "overcharge_ngn": round(overcharge_ngn, 2),
            "overcharge_pct": round((overcharge_ngn / correct_ngn_amount) * 100, 2),
        }

    return result


def _fetch_live_rate(currency: str) -> float:
    """Fetch live NGN exchange rate. Falls back to hardcoded rate on failure."""
    fallbacks = {
        "USD": FALLBACK_USD_NGN,
        "GBP": FALLBACK_GBP_NGN,
        "EUR": FALLBACK_EUR_NGN,
    }

    if EXCHANGE_RATE_API_KEY:
        try:
            url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/pair/{currency}/NGN"
            resp = httpx.get(url, timeout=5)
            data = resp.json()
            if data.get("result") == "success":
                rate = data["conversion_rate"]
                print(f"[ForexChecker] Live rate: 1 {currency} = ₦{rate:,.2f}")
                return rate
        except Exception as e:
            print(f"[ForexChecker] Live rate fetch failed: {e}. Using fallback.")

    rate = fallbacks.get(currency, 1.0)
    print(f"[ForexChecker] Using fallback rate: 1 {currency} = ₦{rate:,.2f}")
    return rate
