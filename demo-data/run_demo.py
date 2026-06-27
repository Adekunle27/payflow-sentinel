"""
PayFlow Sentinel — Demo Runner
Runs preset scenarios for hackathon demo.
Usage: python run_demo.py --scenario [happy_path|fake_invoice|blacklisted_vendor|budget_exceeded|forex_mismatch]
"""

import argparse
import httpx
import json
import time
from datetime import datetime

ERP_URL = "http://localhost:8000"
REQPARSER_URL = "http://localhost:8001"
VENDOR_SCOUT_URL = "http://localhost:8002"
INVOICE_GUARD_URL = "http://localhost:8003"

SCENARIOS = {

    "happy_path": {
        "name": "✅ Happy Path — Standard Office Supply PR",
        "description": "₦2.4M office supply requisition. Clean vendor, valid invoice. Should auto-pay.",
        "pr_text": """
            Purchase Requisition — Operations Department
            Requested by: Chidi Okeke (Operations Manager)
            Department: Operations
            Budget Code: OPS-2026-Q2

            Vendor: Lagos Office Supplies Ltd
            CAC: RC-234567

            Items Required:
            - HP LaserJet Paper A4 (80gsm), 200 reams @ ₦3,500/ream = ₦700,000
            - Pilot G2 Pens (Blue, Box of 12), 50 boxes @ ₦4,800/box = ₦240,000
            - Stapler HD-50, 30 units @ ₦8,500/unit = ₦255,000
            - Printer Toner HP 85A, 40 cartridges @ ₦28,000/cartridge = ₦1,120,000
            - Filing Cabinet (4-drawer), 1 unit @ ₦85,000 = ₦85,000

            Total: ₦2,400,000
            Urgency: Standard
            Justification: Quarterly office supplies replenishment. Current stock at 15% capacity.
        """,
        "vendor_name": "Lagos Office Supplies Ltd",
        "vendor_cac": "RC-234567",
        "expected_outcome": "AUTO-PAY — Clean invoice, all checks pass",
    },

    "fake_invoice": {
        "name": "🚨 Fake Invoice — Price Inflation + Ghost Line Item",
        "description": "₦4.8M invoice for IT equipment. 23% price inflation. Ghost line item. InvoiceGuard should catch it.",
        "pr_text": """
            Purchase Requisition — IT Department
            Requested by: Emeka Nwosu (IT Manager)
            Department: Information Technology
            Budget Code: IT-2026-Q2

            Vendor: Abuja Tech Solutions Nigeria
            CAC: RC-891234

            Items Required:
            - Dell Latitude 5540 Laptop, 10 units @ ₦380,000/unit = ₦3,800,000
            - Logitech MX Keys Keyboard, 10 units @ ₦55,000/unit = ₦550,000
            - USB-C Hub (7-port), 10 units @ ₦35,000/unit = ₦350,000

            Total: ₦4,700,000
            Urgency: Standard
        """,
        "invoice_override": {
            "line_items": [
                {"description": "Dell Latitude 5540 Laptop", "quantity": 10, "unit": "unit", "unit_price_ngn": 467400, "total_ngn": 4674000},
                {"description": "Logitech MX Keys Keyboard", "quantity": 10, "unit": "unit", "unit_price_ngn": 55000, "total_ngn": 550000},
                {"description": "USB-C Hub (7-port)", "quantity": 10, "unit": "unit", "unit_price_ngn": 35000, "total_ngn": 350000},
                {"description": "Extended Warranty Premium", "quantity": 1, "unit": "service", "unit_price_ngn": 500000, "total_ngn": 500000},
            ],
            "total_value_ngn": 6074000,  # 29% inflated + ghost line
        },
        "vendor_name": "Abuja Tech Solutions Nigeria",
        "vendor_cac": "RC-891234",
        "expected_outcome": "ESCALATE/REJECT — Price inflation 29%, ghost line item detected",
    },

    "blacklisted_vendor": {
        "name": "🔴 Blacklisted Vendor — Name Impersonation Attack",
        "description": "PR uses 'Lagos Office Suppliies Ltd' (extra 'i') — mimicking legitimate vendor. VendorScout should catch it.",
        "pr_text": """
            Purchase Requisition — Admin Department
            Requested by: Funke Adeyemi
            Department: Operations
            Budget Code: OPS-2026-Q2

            Vendor: Lagos Office Suppliies Ltd
            CAC: RC-234568

            Items: Office supplies, bulk order
            Total: ₦1,800,000
            Urgency: Urgent
        """,
        "vendor_name": "Lagos Office Suppliies Ltd",
        "vendor_cac": "RC-234568",
        "expected_outcome": "REJECTED — Vendor name matches blacklisted impersonator",
    },

    "budget_exceeded": {
        "name": "💼 Budget Exceeded — CFO Approval Required",
        "description": "₦8.7M construction materials PR. Exceeds ₦5M threshold, routes to CFO.",
        "pr_text": """
            Purchase Requisition — Construction Projects
            Requested by: Babatunde Lawal (Project Manager)
            Department: Construction Projects
            Budget Code: CONST-2026

            Vendor: Kano Construction & Engineering Co.
            CAC: RC-445678

            Items Required:
            - Reinforced Steel Bars (12mm), 50 tons @ ₦95,000/ton = ₦4,750,000
            - Portland Cement (50kg bags), 500 bags @ ₦8,500/bag = ₦4,250,000
            - Gravel (20mm), 30 tons @ ₦35,000/ton = ₦1,050,000
            - Construction Sand, 20 tons @ ₦18,000/ton = ₦360,000

            Subtotal: ₦10,410,000
            Discount: -₦1,710,000
            Total: ₦8,700,000
            Urgency: Standard
            Justification: Phase 2 building materials for Abuja office expansion project.
        """,
        "vendor_name": "Kano Construction & Engineering Co.",
        "vendor_cac": "RC-445678",
        "expected_outcome": "ROUTES TO CFO APPROVAL — Exceeds ₦5M threshold",
    },

    "forex_mismatch": {
        "name": "💱 Forex Mismatch — Inflated USD/NGN Rate",
        "description": "USD invoice with inflated FX rate. Vendor claims ₦1,750/USD but actual rate is ₦1,580/USD.",
        "pr_text": """
            Purchase Requisition — IT Department
            Requested by: Kelechi Obi
            Department: Information Technology
            Budget Code: IT-2026-Q2

            Vendor: Abuja Tech Solutions Nigeria
            Items: 10x Adobe Creative Cloud Annual License @ $250/license = $2,500 USD
            Approximate NGN: ₦3,950,000
            Urgency: Standard
        """,
        "invoice_override": {
            "currency": "USD",
            "fx_rate_claimed": 1750.0,   # Inflated — actual is ~1580
            "total_value_ngn": 4375000,  # $2,500 × ₦1,750 (inflated)
        },
        "vendor_name": "Abuja Tech Solutions Nigeria",
        "vendor_cac": "RC-891234",
        "expected_outcome": "ESCALATE — FX rate inflated by ~10.7%, overcharge of ~₦425,000",
    },
}


def print_header(scenario_name: str):
    print("\n" + "═" * 60)
    print(f"  PayFlow Sentinel — Demo Scenario")
    print(f"  {scenario_name}")
    print("═" * 60)


def run_scenario(scenario_key: str):
    scenario = SCENARIOS.get(scenario_key)
    if not scenario:
        print(f"Unknown scenario: {scenario_key}")
        print(f"Available: {list(SCENARIOS.keys())}")
        return

    print_header(scenario["name"])
    print(f"\n📋 Description: {scenario['description']}")
    print(f"🎯 Expected: {scenario['expected_outcome']}\n")

    # Step 1: Parse PR
    print("─" * 40)
    print("STEP 1: ReqParser Agent parsing requisition...")
    time.sleep(0.5)

    try:
        parse_resp = httpx.post(
            f"{REQPARSER_URL}/parse",
            json={"raw_text": scenario["pr_text"], "requisition_id": f"PR-DEMO-{scenario_key.upper()}"},
            timeout=60,
        )
        parsed_pr = parse_resp.json()
        print(f"  ✓ Vendor: {parsed_pr.get('vendor_name')}")
        print(f"  ✓ Total: ₦{parsed_pr.get('estimated_value_ngn', 0):,.0f}")
        print(f"  ✓ Category: {parsed_pr.get('category')}")
        print(f"  ✓ Flags: {parsed_pr.get('flags', [])}")
    except Exception as e:
        print(f"  ⚠ ReqParser not running. Using mock data. ({e})")
        parsed_pr = {
            "vendor_name": scenario["vendor_name"],
            "vendor_cac": scenario.get("vendor_cac"),
            "estimated_value_ngn": 2400000,
            "category": "office_supplies",
            "flags": [],
        }

    # Step 2: VendorScout
    print("\nSTEP 2: VendorScout agent analyzing vendor...")
    time.sleep(0.5)

    try:
        scout_resp = httpx.post(
            f"{VENDOR_SCOUT_URL}/scout",
            json={
                "vendor_name": scenario["vendor_name"],
                "cac_number": scenario.get("vendor_cac"),
                "category": parsed_pr.get("category", "other"),
                "proposed_value_ngn": parsed_pr.get("estimated_value_ngn", 0),
            },
            timeout=120,
        )
        scout = scout_resp.json()
        print(f"  ✓ Trust Score: {scout.get('trust_score')}/100")
        print(f"  ✓ Blacklisted: {scout.get('is_blacklisted')}")
        print(f"  ✓ Recommendation: {scout.get('recommendation', '').upper()}")
        if scout.get("is_blacklisted"):
            print(f"\n  🔴 VENDOR BLOCKED: {scout.get('blacklist_reason', 'Blacklist match')}")
            print("  ✗ Process TERMINATED — Fraudulent vendor detected")
            return
    except Exception as e:
        print(f"  ⚠ VendorScout not running. Using mock. ({e})")
        print(f"  Mock trust score: 75 | Recommendation: APPROVE")

    print(f"\n✅ Demo scenario '{scenario_key}' completed.")
    print(f"📌 Expected outcome: {scenario['expected_outcome']}")
    print("═" * 60)


def list_scenarios():
    print("\n📋 Available Demo Scenarios:\n")
    for key, s in SCENARIOS.items():
        print(f"  --scenario {key}")
        print(f"    {s['name']}")
        print(f"    Expected: {s['expected_outcome']}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PayFlow Sentinel Demo Runner")
    parser.add_argument("--scenario", type=str, help="Scenario to run")
    parser.add_argument("--list", action="store_true", help="List all scenarios")
    args = parser.parse_args()

    if args.list or not args.scenario:
        list_scenarios()
    else:
        run_scenario(args.scenario)
