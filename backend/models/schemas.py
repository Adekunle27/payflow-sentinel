"""
PayFlow Sentinel — Data Models / Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class VendorStatus(str, Enum):
    ACTIVE = "active"
    BLACKLISTED = "blacklisted"
    PENDING_REVIEW = "pending_review"
    SUSPENDED = "suspended"


class PRCategory(str, Enum):
    IT_EQUIPMENT = "it_equipment"
    OFFICE_SUPPLIES = "office_supplies"
    PROFESSIONAL_SERVICES = "professional_services"
    CONSTRUCTION = "construction"
    CATERING = "catering"
    LOGISTICS = "logistics"
    MAINTENANCE = "maintenance"
    OTHER = "other"


class POStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT_TO_VENDOR = "sent_to_vendor"
    GOODS_RECEIVED = "goods_received"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"


class InvoiceStatus(str, Enum):
    RECEIVED = "received"
    UNDER_REVIEW = "under_review"
    MATCHED = "matched"
    EXCEPTION = "exception"
    APPROVED = "approved"
    PAID = "paid"
    REJECTED = "rejected"


class Currency(str, Enum):
    NGN = "NGN"
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"


# ─── Vendor Models ───────────────────────────────────────────────

class VendorCreate(BaseModel):
    name: str
    cac_number: Optional[str] = None
    email: str
    phone: str
    address: str
    category: PRCategory
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None


class Vendor(VendorCreate):
    id: str
    status: VendorStatus = VendorStatus.ACTIVE
    trust_score: float = Field(default=50.0, ge=0, le=100)
    transaction_count: int = 0
    total_value_ngn: float = 0.0
    registered_at: datetime
    blacklist_reason: Optional[str] = None


# ─── Purchase Requisition Models ─────────────────────────────────

class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price_ngn: float
    total_ngn: float
    unit: str = "unit"


class PurchaseRequisition(BaseModel):
    id: str
    requester_name: str
    requester_email: str
    department: str
    budget_code: str
    category: PRCategory
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    line_items: List[LineItem]
    total_value_ngn: float
    currency: Currency = Currency.NGN
    fx_rate: Optional[float] = None        # If USD invoice, NGN/USD rate
    urgency: str = "standard"              # standard | urgent | critical
    justification: str
    submitted_at: datetime
    status: str = "submitted"


# ─── Purchase Order Models ────────────────────────────────────────

class PurchaseOrderCreate(BaseModel):
    requisition_id: str
    vendor_id: str
    line_items: List[LineItem]
    total_value_ngn: float
    currency: Currency = Currency.NGN
    delivery_date: Optional[str] = None
    terms: str = "Net 30"


class PurchaseOrder(PurchaseOrderCreate):
    id: str
    po_number: str
    status: POStatus = POStatus.DRAFT
    created_at: datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


# ─── Goods Receipt Models ─────────────────────────────────────────

class GoodsReceiptNote(BaseModel):
    id: str
    po_id: str
    received_by: str
    received_at: datetime
    line_items: List[LineItem]    # Actual quantities received
    total_value_ngn: float
    notes: Optional[str] = None


# ─── Invoice Models ───────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    po_id: str
    vendor_id: str
    invoice_number: str
    invoice_date: str
    line_items: List[LineItem]
    total_value_ngn: float
    currency: Currency = Currency.NGN
    fx_rate_claimed: Optional[float] = None   # FX rate vendor claims


class Invoice(InvoiceCreate):
    id: str
    status: InvoiceStatus = InvoiceStatus.RECEIVED
    received_at: datetime
    risk_score: Optional[float] = None
    risk_reasons: Optional[List[str]] = None
    match_result: Optional[str] = None       # matched | exception
    match_delta_pct: Optional[float] = None
    processed_by_agent: bool = False


# ─── Payment Models ───────────────────────────────────────────────

class PaymentCreate(BaseModel):
    invoice_id: str
    po_id: str
    vendor_id: str
    amount_ngn: float
    payment_method: str = "bank_transfer"
    approved_by: str


class Payment(PaymentCreate):
    id: str
    payment_reference: str
    status: str = "completed"
    executed_at: datetime
    audit_log: List[str] = []


# ─── Agent Response Models ────────────────────────────────────────

class ReqParserOutput(BaseModel):
    """Structured output from ReqParser agent."""
    vendor_name: str
    vendor_cac: Optional[str]
    line_items: List[LineItem]
    category: PRCategory
    estimated_value_ngn: float
    budget_code: str
    urgency: str
    confidence: float = Field(ge=0, le=1)
    raw_text_used: str


class VendorScoutOutput(BaseModel):
    """Structured output from VendorScout agent."""
    vendor_id: Optional[str]
    vendor_name: str
    trust_score: float = Field(ge=0, le=100)
    is_blacklisted: bool
    blacklist_reason: Optional[str]
    duplicate_risk: bool
    similar_vendors: List[str]
    recommendation: str   # approve | reject | review
    reasoning: str


class InvoiceGuardOutput(BaseModel):
    """Structured output from InvoiceGuard agent."""
    invoice_id: str
    risk_score: float = Field(ge=0, le=100)
    match_status: str   # matched | exception
    po_match: bool
    grn_match: bool
    price_delta_pct: float
    forex_valid: bool
    forex_claimed_rate: Optional[float]
    forex_actual_rate: Optional[float]
    fraud_signals: List[str]
    recommendation: str   # auto_pay | escalate | reject
    reasoning: str
