"""
PayFlow Sentinel — Agent 2: VendorScout
Built with CrewAI — two sub-agents: Researcher + Risk Scorer.

Validates vendor legitimacy, detects duplicates/impersonation,
and produces a trust score + recommendation.
"""

import os
import json
import httpx
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type
from datetime import datetime
from fastapi import FastAPI, HTTPException

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://localhost:8000")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY or ""

# ─── Custom Tools ─────────────────────────────────────────────────

class VendorSearchInput(BaseModel):
    vendor_name: str = Field(description="Name of vendor to search for")

class VendorRegistrySearchTool(BaseTool):
    name: str = "vendor_registry_search"
    description: str = "Search the internal vendor registry by name. Returns matching vendors with trust scores and transaction history."
    args_schema: Type[BaseModel] = VendorSearchInput

    def _run(self, vendor_name: str) -> str:
        resp = httpx.get(f"{ERP_BASE_URL}/vendors/search/name", params={"q": vendor_name}, timeout=10)
        data = resp.json()
        if not data:
            return f"No vendors found matching '{vendor_name}' in registry."
        return json.dumps(data, indent=2)


class BlacklistCheckInput(BaseModel):
    vendor_name: str = Field(description="Vendor name to check against blacklist")
    cac_number: str = Field(default=None, description="CAC registration number (optional)")

class BlacklistCheckTool(BaseTool):
    name: str = "blacklist_check"
    description: str = "Check if a vendor name or CAC number appears on the fraud blacklist."
    args_schema: Type[BaseModel] = BlacklistCheckInput

    def _run(self, vendor_name: str, cac_number: str = None) -> str:
        params = {"name": vendor_name}
        if cac_number:
            params["cac"] = cac_number
        resp = httpx.get(f"{ERP_BASE_URL}/vendors/blacklist/check", params=params, timeout=10)
        return json.dumps(resp.json(), indent=2)


class AllVendorsInput(BaseModel):
    category: str = Field(default=None, description="Optional category filter")

class GetAllVendorsTool(BaseTool):
    name: str = "get_all_vendors"
    description: str = "Get all registered vendors, optionally filtered by category."
    args_schema: Type[BaseModel] = AllVendorsInput

    def _run(self, category: str = None) -> str:
        params = {}
        if category:
            params["category"] = category
        resp = httpx.get(f"{ERP_BASE_URL}/vendors/", params=params, timeout=10)
        return json.dumps(resp.json(), indent=2)


# ─── CrewAI Agents ────────────────────────────────────────────────

researcher = Agent(
    role="Vendor Research Specialist",
    goal="Find and verify information about the vendor in question. Check if they exist in registry, search for similar names, and verify CAC registration.",
    backstory="""You are an expert procurement analyst at a major Nigerian conglomerate. 
    You have seen countless cases of vendor fraud — name impersonation (e.g. 'Dangote Supplies' vs 'Dangotee Supplies'), 
    ghost vendors, and shell companies. Your job is to gather all available facts about a vendor before making any recommendation.""",
    tools=[VendorRegistrySearchTool(), BlacklistCheckTool(), GetAllVendorsTool()],
    llm="claude-sonnet-4-6",
    verbose=True,
    allow_delegation=False,
)

risk_scorer = Agent(
    role="Vendor Risk Assessment Officer",
    goal="Based on the researcher's findings, produce a definitive trust score (0-100) and a clear recommendation (approve/reject/review).",
    backstory="""You are a fraud risk specialist with 15 years of experience in Nigerian enterprise procurement. 
    You understand common fraud patterns: name-similarity scams, CAC number reuse, round-number invoicing, 
    and ghost vendor schemes. You produce precise, defensible risk scores with clear reasoning.""",
    tools=[],
    llm="claude-sonnet-4-6",
    verbose=True,
    allow_delegation=False,
)


# ─── Tasks ────────────────────────────────────────────────────────

def create_tasks(vendor_name: str, cac_number: str, category: str, proposed_value_ngn: float):

    research_task = Task(
        description=f"""Research the vendor: '{vendor_name}' (CAC: {cac_number or 'Not provided'})
        
        Steps:
        1. Search vendor registry for exact and similar names
        2. Check blacklist for this vendor name and CAC number
        3. Look at all vendors in category '{category}' for any suspicious duplicates
        4. Note the proposed transaction value: ₦{proposed_value_ngn:,.0f}
        
        Report ALL findings including: registry match (yes/no), blacklist status, similar-name vendors found, 
        existing trust scores, and any red flags.""",
        expected_output="A detailed research report covering registry status, blacklist check results, similar vendor names found, and all relevant facts.",
        agent=researcher,
    )

    scoring_task = Task(
        description=f"""Based on the researcher's findings for vendor '{vendor_name}', produce a risk assessment.
        
        Calculate trust score (0-100) where:
        - 80-100: Clean record, established vendor, matches registry exactly
        - 60-79: Minor concerns, needs light review
        - 40-59: Multiple concerns, human review required
        - 20-39: High risk, likely fraud — recommend rejection
        - 0-19: Blacklisted or confirmed fraud — reject immediately
        
        Consider: name similarity to blacklisted vendors, CAC validity, transaction history, 
        proposed value vs. historical transactions, category match.
        
        RESPOND ONLY WITH THIS JSON (no other text):
        {{
          "vendor_name": "{vendor_name}",
          "vendor_id": "id from registry or null",
          "trust_score": 0,
          "is_blacklisted": false,
          "blacklist_reason": null,
          "duplicate_risk": false,
          "similar_vendors": [],
          "recommendation": "approve|reject|review",
          "risk_factors": [],
          "positive_factors": [],
          "reasoning": "2-3 sentence summary"
        }}""",
        expected_output="JSON risk assessment with trust score, recommendation, and reasoning.",
        agent=risk_scorer,
        context=[research_task],
    )

    return [research_task, scoring_task]


# ─── Main Scout Function ──────────────────────────────────────────

def scout_vendor(
    vendor_name: str,
    cac_number: str = None,
    category: str = "other",
    proposed_value_ngn: float = 0,
) -> dict:
    print(f"\n[VendorScout] Analyzing vendor: {vendor_name}")

    crew = Crew(
        agents=[researcher, risk_scorer],
        tasks=create_tasks(vendor_name, cac_number, category, proposed_value_ngn),
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()
    raw_output = str(result)

    # Parse JSON from output
    import re
    json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
    if json_match:
        parsed = json.loads(json_match.group())
    else:
        # Fallback structure if parsing fails
        parsed = {
            "vendor_name": vendor_name,
            "vendor_id": None,
            "trust_score": 50.0,
            "is_blacklisted": False,
            "blacklist_reason": None,
            "duplicate_risk": False,
            "similar_vendors": [],
            "recommendation": "review",
            "risk_factors": ["Unable to parse full crew output — defaulting to manual review"],
            "positive_factors": [],
            "reasoning": raw_output[:300],
        }

    parsed["scouted_at"] = datetime.utcnow().isoformat()
    parsed["agent"] = "VendorScout-CrewAI-v1"

    print(f"[VendorScout] ✓ Trust score: {parsed.get('trust_score')} | Recommendation: {parsed.get('recommendation')}")
    return parsed


# ─── FastAPI wrapper ──────────────────────────────────────────────

app = FastAPI(title="VendorScout Agent API")

class ScoutRequest(BaseModel):
    vendor_name: str
    cac_number: str = None
    category: str = "other"
    proposed_value_ngn: float = 0

@app.post("/scout")
def scout_endpoint(req: ScoutRequest):
    try:
        result = scout_vendor(req.vendor_name, req.cac_number, req.category, req.proposed_value_ngn)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "agent": "VendorScout-CrewAI-v1"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
