"""
PayFlow Sentinel — Mock ERP Backend
FastAPI server simulating an enterprise ERP system.
Provides vendor registry, PO management, invoice store, and payment logging.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import json
import os
from datetime import datetime

from routes.vendors import router as vendors_router
from routes.purchase_orders import router as po_router
from routes.invoices import router as invoices_router
from routes.payments import router as payments_router

app = FastAPI(
    title="PayFlow Sentinel — Mock ERP API",
    description="Simulated ERP system for PayFlow Sentinel P2P orchestration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vendors_router, prefix="/vendors", tags=["Vendors"])
app.include_router(po_router, prefix="/purchase-orders", tags=["Purchase Orders"])
app.include_router(invoices_router, prefix="/invoices", tags=["Invoices"])
app.include_router(payments_router, prefix="/payments", tags=["Payments"])


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "PayFlow Sentinel Mock ERP",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": ["/vendors", "/purchase-orders", "/invoices", "/payments", "/docs"],
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/budget-codes", tags=["Budget"])
def get_budget_codes():
    """Return all valid department budget codes."""
    data_path = os.path.join(os.path.dirname(__file__), "data", "budget_codes.json")
    with open(data_path) as f:
        return json.load(f)


@app.get("/budget-codes/{code}/balance", tags=["Budget"])
def get_budget_balance(code: str):
    """Return available budget for a given budget code."""
    data_path = os.path.join(os.path.dirname(__file__), "data", "budget_codes.json")
    with open(data_path) as f:
        codes = json.load(f)
    match = next((c for c in codes if c["code"] == code), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Budget code {code} not found")
    return {
        "code": code,
        "department": match["department"],
        "allocated": match["allocated_ngn"],
        "spent": match["spent_ngn"],
        "available": match["allocated_ngn"] - match["spent_ngn"],
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
