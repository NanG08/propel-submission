# tests/test_step2_money_gate.py
"""Tests for deterministic money gate and safety logic (STEP 2)."""

from pathlib import Path
import pytest

from app.schemas import TicketInput, LLMTriageDraft, TriageCategory, SeverityLevel
from app.money_gate import apply_safety_gates, detect_prompt_injection

# Helper to load tickets dict by id
def load_all_tickets() -> dict[str, dict]:
    json_path = Path(__file__).parents[1] / "docs" / "dhaba_tickets.json"
    if not json_path.is_file():
        json_path = Path(__file__).parents[2] / "propel-dhaba-submission" / "docs" / "dhaba_tickets.json"
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {t["id"]: t for t in data["tickets"]}

TICKETS = load_all_tickets()

def base_llm_draft(category: TriageCategory, severity: SeverityLevel, wants_refund: bool, confidence: float = 0.95):
    return LLMTriageDraft(
        category=category,
        severity=severity,
        user_wants_refund=wants_refund,
        reply_draft="Thank you.",
        needs_human=False,
        confidence=confidence,
        prompt_injection_detected=False,
        reasoning="",
    )

def test_t_1001_monthly_refund_approved():
    ticket = TicketInput.model_validate(TICKETS["T-1001"])
    llm = base_llm_draft(TriageCategory.REFUND_REQUEST, SeverityLevel.P1_HIGH, True)
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is True
    assert response.refund.amount_inr == 249
    assert response.refund.payment_id == "pay_A2"
    assert response.needs_human is False

def test_t_1003_prompt_injection_blocked():
    ticket = TicketInput.model_validate(TICKETS["T-1003"])
    llm = base_llm_draft(TriageCategory.REFUND_REQUEST, SeverityLevel.P0_CRITICAL, True)
    detected, _ = detect_prompt_injection(ticket.subject, ticket.body)
    assert detected
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is False
    assert "security guardrail" in response.refund.reason.lower()
    assert response.needs_human is True

def test_t_1005_initiated_payment():
    ticket = TicketInput.model_validate(TICKETS["T-1005"])
    llm = base_llm_draft(TriageCategory.REFUND_REQUEST, SeverityLevel.P1_HIGH, True)
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is False
    assert "initiated" in response.refund.reason.lower()
    assert response.needs_human is True

def test_t_1006_annual_high_value_gate():
    ticket = TicketInput.model_validate(TICKETS["T-1006"])
    llm = base_llm_draft(TriageCategory.REFUND_REQUEST, SeverityLevel.P0_CRITICAL, True)
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is False
    assert "exceeds auto‑refund cap" in response.refund.reason.lower()
    assert response.needs_human is True

def test_t_1009_double_charge():
    ticket = TicketInput.model_validate(TICKETS["T-1009"])
    llm = base_llm_draft(TriageCategory.REFUND_REQUEST, SeverityLevel.P1_HIGH, True)
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is False
    assert "only one successful" in response.refund.reason.lower()
    # human review not forced by rule 5, default needs_human stays False
    assert response.needs_human is False

def test_t_1011_prompt_exfiltration_blocked():
    ticket = TicketInput.model_validate(TICKETS["T-1011"])
    llm = base_llm_draft(TriageCategory.PRE_SALES_QUERY, SeverityLevel.P2_MEDIUM, True)
    detected, _ = detect_prompt_injection(ticket.subject, ticket.body)
    assert detected
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is False
    assert "security guardrail" in response.refund.reason.lower()
    assert response.needs_human is True

def test_t_1012_usage_gate_blocks_refund():
    ticket = TicketInput.model_validate(TICKETS["T-1012"])
    llm = base_llm_draft(TriageCategory.REFUND_REQUEST, SeverityLevel.P1_HIGH, True)
    response = apply_safety_gates(ticket, llm)
    assert response.refund.approved is False
    assert "app opens" in response.refund.reason.lower()
    assert response.needs_human is True
