"""
PayFlow Sentinel — InvoiceGuard: 3-Way Match Engine
★ Built with Claude Code via UiPath for Coding Agents ★

Reconciles Purchase Order / Goods Receipt Note / Invoice
Flags any variance beyond the 2% tolerance threshold.
"""

from typing import List, Dict


def perform_three_way_match(
    po_line_items: List[Dict],
    grn_line_items: List[Dict],
    invoice_line_items: List[Dict],
    po_total: float,
    grn_total: float,
    invoice_total: float,
    tolerance_pct: float = 2.0,
) -> Dict:
    """
    Perform 3-way match between PO, GRN, and Invoice.
    Returns match status and detailed delta analysis.
    """

    results = {
        "po_total": po_total,
        "grn_total": grn_total,
        "invoice_total": invoice_total,
        "tolerance_pct": tolerance_pct,
        "po_match": False,
        "grn_match": False,
        "delta_pct": 0.0,
        "status": "matched",
        "line_item_exceptions": [],
        "total_exceptions": [],
    }

    # ── Total-Level Match ─────────────────────────────────────────

    # PO vs Invoice
    if po_total > 0:
        po_inv_delta = abs(invoice_total - po_total) / po_total * 100
    else:
        po_inv_delta = 100.0

    # GRN vs Invoice
    if grn_total > 0:
        grn_inv_delta = abs(invoice_total - grn_total) / grn_total * 100
    else:
        grn_inv_delta = 100.0

    results["po_inv_delta_pct"] = round(po_inv_delta, 2)
    results["grn_inv_delta_pct"] = round(grn_inv_delta, 2)
    results["delta_pct"] = round(max(po_inv_delta, grn_inv_delta), 2)

    results["po_match"] = po_inv_delta <= tolerance_pct
    results["grn_match"] = grn_inv_delta <= tolerance_pct

    if not results["po_match"]:
        results["total_exceptions"].append({
            "type": "po_invoice_mismatch",
            "po_total": po_total,
            "invoice_total": invoice_total,
            "delta_pct": po_inv_delta,
            "delta_ngn": abs(invoice_total - po_total),
        })

    if not results["grn_match"]:
        results["total_exceptions"].append({
            "type": "grn_invoice_mismatch",
            "grn_total": grn_total,
            "invoice_total": invoice_total,
            "delta_pct": grn_inv_delta,
            "delta_ngn": abs(invoice_total - grn_total),
        })

    # ── Line-Item Level Match ─────────────────────────────────────

    po_items = {_normalize_desc(item["description"]): item for item in (po_line_items or [])}
    inv_items = {_normalize_desc(item["description"]): item for item in (invoice_line_items or [])}

    for desc, inv_item in inv_items.items():
        po_item = po_items.get(desc)

        if not po_item:
            # Invoice has a line item not in PO — ghost line
            results["line_item_exceptions"].append({
                "type": "ghost_line_item",
                "description": inv_item["description"],
                "invoice_amount": inv_item.get("total_ngn", 0),
                "severity": "high",
            })
            continue

        # Price per unit check
        po_unit_price = po_item.get("unit_price_ngn", 0)
        inv_unit_price = inv_item.get("unit_price_ngn", 0)

        if po_unit_price > 0:
            price_delta = abs(inv_unit_price - po_unit_price) / po_unit_price * 100
            if price_delta > tolerance_pct:
                results["line_item_exceptions"].append({
                    "type": "unit_price_mismatch",
                    "description": inv_item["description"],
                    "po_unit_price": po_unit_price,
                    "invoice_unit_price": inv_unit_price,
                    "delta_pct": round(price_delta, 2),
                    "delta_ngn": abs(inv_unit_price - po_unit_price),
                    "severity": "high" if price_delta > 10 else "medium",
                })

        # Quantity check
        po_qty = po_item.get("quantity", 0)
        inv_qty = inv_item.get("quantity", 0)
        if po_qty > 0 and abs(inv_qty - po_qty) / po_qty * 100 > tolerance_pct:
            results["line_item_exceptions"].append({
                "type": "quantity_mismatch",
                "description": inv_item["description"],
                "po_quantity": po_qty,
                "invoice_quantity": inv_qty,
                "severity": "medium",
            })

    # ── Final Status ──────────────────────────────────────────────

    has_exceptions = (
        not results["po_match"] or
        not results["grn_match"] or
        len(results["line_item_exceptions"]) > 0
    )

    results["status"] = "exception" if has_exceptions else "matched"
    results["exception_count"] = len(results["line_item_exceptions"]) + len(results["total_exceptions"])

    return results


def _normalize_desc(desc: str) -> str:
    """Normalize description for comparison — lowercase, strip extras."""
    return " ".join(desc.lower().strip().split())
