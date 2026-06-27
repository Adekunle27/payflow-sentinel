"""
PayFlow Sentinel — Agent 1: ReqParser
Built with LangChain + Claude Sonnet via UiPath Agent Builder.

Takes raw purchase requisition text (email, form, PDF extract) and returns
structured procurement JSON for downstream BPMN processing.
"""

import os
import json
import re
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    api_key=ANTHROPIC_API_KEY,
    temperature=0,
    max_tokens=2000,
)

# ─── Tools ────────────────────────────────────────────────────────

@tool
def get_budget_codes() -> str:
    """Retrieve all valid department budget codes from ERP."""
    resp = httpx.get(f"{ERP_BASE_URL}/budget-codes", timeout=10)
    return json.dumps(resp.json())


@tool
def check_budget_balance(budget_code: str) -> str:
    """Check available budget for a specific budget code."""
    resp = httpx.get(f"{ERP_BASE_URL}/budget-codes/{budget_code}/balance", timeout=10)
    if resp.status_code == 404:
        return json.dumps({"error": f"Budget code {budget_code} not found"})
    return json.dumps(resp.json())


@tool
def lookup_vendor_by_name(vendor_name: str) -> str:
    """Search vendor registry for a vendor by name."""
    resp = httpx.get(f"{ERP_BASE_URL}/vendors/search/name", params={"q": vendor_name}, timeout=10)
    return json.dumps(resp.json())


# ─── System Prompt ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are ReqParser, an AI procurement assistant for a Nigerian enterprise.
Your job is to parse raw purchase requisition text and extract structured procurement data.

RULES:
1. Always extract: vendor name, line items (description, quantity, unit, unit_price_ngn, total_ngn), category, estimated total in NGN, budget code, urgency
2. If amounts are in USD, convert using approximate rate of ₦1,580/USD (flag as FX if so)
3. Budget codes follow format: DEPT-YEAR-QX (e.g. OPS-2026-Q2). Infer from department if not stated.
4. Categories: it_equipment, office_supplies, professional_services, construction, catering, logistics, maintenance, other
5. Urgency: standard (default), urgent (needed within 1 week), critical (needed within 24h)
6. Confidence: rate 0.0-1.0 how complete/clear the requisition was

ALWAYS respond with ONLY valid JSON in this exact structure:
{
  "vendor_name": "string",
  "vendor_cac": "string or null",
  "line_items": [
    {"description": "...", "quantity": 0, "unit": "...", "unit_price_ngn": 0, "total_ngn": 0}
  ],
  "category": "...",
  "estimated_value_ngn": 0,
  "budget_code": "...",
  "urgency": "standard|urgent|critical",
  "currency_original": "NGN|USD|GBP|EUR",
  "fx_rate_used": null,
  "confidence": 0.0,
  "flags": [],
  "raw_text_used": "first 200 chars of input"
}

FLAGS to include when relevant:
- "fx_conversion_applied" — if currency was not NGN
- "budget_code_inferred" — if budget code was guessed from department
- "vendor_not_found_in_registry" — if vendor lookup returned no results
- "incomplete_line_items" — if quantities or prices were missing
- "exceeds_5m_threshold" — if total > ₦5,000,000 (triggers CFO approval)
- "exceeds_20m_threshold" — if total > ₦20,000,000 (triggers Board approval)
"""

# ─── Agent Setup ──────────────────────────────────────────────────

tools = [get_budget_codes, check_budget_balance, lookup_vendor_by_name]
agent = create_react_agent(llm, tools)


# ─── Main Parser Function ─────────────────────────────────────────

def parse_requisition(raw_text: str, requisition_id: str = None) -> dict:
    """
    Parse a raw purchase requisition and return structured JSON.
    Called by UiPath Maestro BPMN via HTTP trigger.
    """
    print(f"\n[ReqParser] Processing requisition: {requisition_id or 'UNKNOWN'}")
    print(f"[ReqParser] Input length: {len(raw_text)} chars")

    messages = [
        {"role": "user", "content": f"Parse this purchase requisition:\n\n{raw_text}"}
    ]

    result = agent.invoke({"messages": messages})
    final_message = result["messages"][-1].content

    # Extract JSON from response
    try:
        # Try direct parse first
        parsed = json.loads(final_message)
    except json.JSONDecodeError:
        # Extract JSON block if wrapped in text
        json_match = re.search(r'\{.*\}', final_message, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
        else:
            raise ValueError(f"ReqParser returned non-JSON: {final_message[:200]}")

    # Add metadata
    parsed["requisition_id"] = requisition_id
    parsed["parsed_at"] = datetime.utcnow().isoformat()
    parsed["agent"] = "ReqParser-v1"

    # Auto-flag high-value PRs
    total = parsed.get("estimated_value_ngn", 0)
    flags = parsed.get("flags", [])
    if total > 20_000_000 and "exceeds_20m_threshold" not in flags:
        flags.append("exceeds_20m_threshold")
    elif total > 5_000_000 and "exceeds_5m_threshold" not in flags:
        flags.append("exceeds_5m_threshold")
    parsed["flags"] = flags

    print(f"[ReqParser] ✓ Parsed. Total: ₦{total:,.0f} | Category: {parsed.get('category')} | Confidence: {parsed.get('confidence')}")
    return parsed


# ─── FastAPI wrapper (UiPath calls this via API Workflow) ─────────

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ReqParser Agent API")

class ParseRequest(BaseModel):
    raw_text: str
    requisition_id: str = None

@app.post("/parse")
def parse_endpoint(req: ParseRequest):
    try:
        result = parse_requisition(req.raw_text, req.requisition_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "agent": "ReqParser-v1"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
