# schemas.py
"""Pydantic v2 schemas for Dhaba ticket triage.
All models are strict (extra='forbid') to prevent unexpected fields.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

# Enums for purchase types and status
class PurchaseType(str, Enum):
    trial = "trial"
    renewal = "renewal"

class PurchaseStatus(str, Enum):
    initiated = "initiated"
    failed = "failed"
    successful = "successful"
    renewal = "renewal"

class Purchase(BaseModel):
    id: str
    type: PurchaseType
    amount_inr: int = Field(ge=0)
    status: PurchaseStatus
    at: str

    model_config = ConfigDict(extra="forbid")

class TicketInput(BaseModel):
    id: str
    received_at: str
    subject: str
    body: str
    purchases: List[Purchase]
    app_opens_since_renewal: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")

# Output enums
class TriageCategory(str, Enum):
    REFUND_REQUEST = "REFUND_REQUEST"
    BILLING_DISPUTE = "BILLING_DISPUTE"
    BUG_REPORT = "BUG_REPORT"
    ACCOUNT_ISSUE = "ACCOUNT_ISSUE"
    CANCELLATION = "CANCELLATION"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    INVOICE_REQUEST = "INVOICE_REQUEST"
    PRE_SALES_QUERY = "PRE_SALES_QUERY"
    SECURITY_OR_ABUSE = "SECURITY_OR_ABUSE"

class SeverityLevel(str, Enum):
    """Severity criteria:
    - P0_CRITICAL: Issues requiring immediate attention (e.g., fraud, security breach).
    - P1_HIGH: High‑impact problems affecting many users or revenue (e.g., payment failure).
    - P2_MEDIUM: Moderate impact, non‑urgent bugs or feature requests.
    - P3_LOW: Minor issues or informational requests.
    """
    P0_CRITICAL = "P0_CRITICAL"
    P1_HIGH = "P1_HIGH"
    P2_MEDIUM = "P2_MEDIUM"
    P3_LOW = "P3_LOW"

class RefundDecision(BaseModel):
    approved: bool
    amount_inr: int = Field(ge=0)
    reason: str
    payment_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class TriageResponse(BaseModel):
    ticket_id: str
    category: TriageCategory
    severity: SeverityLevel
    refund: RefundDecision
    reply_draft: str
    needs_human: bool
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")

# Schema used as a safe output contract for the LLM
class LLMTriageDraft(BaseModel):
    category: TriageCategory
    severity: SeverityLevel
    user_wants_refund: bool
    reply_draft: str
    needs_human: bool
    confidence: float = Field(ge=0.0, le=1.0)
    prompt_injection_detected: bool
    reasoning: str

    model_config = ConfigDict(extra="forbid")
