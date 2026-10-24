# tests/test_step3_idempotency.py
"""Tests for the SQLite idempotency store (STEP 3)."""

from pathlib import Path
import json
import pytest

from app.schemas import TicketInput, TriageResponse, RefundDecision, TriageCategory, SeverityLevel
from app.idempotency import IdempotencyStore, IdempotencyConflictError

# Helper to load tickets dict by id – same as previous test helpers
def load_all_tickets() -> dict[str, dict]:
    json_path = Path(__file__).parents[1] / "propel-dhaba-submission" / "docs" / "dhaba_tickets.json"
    if not json_path.is_file():
        json_path = Path(__file__).parents[2] / "propel-dhaba-submission" / "docs" / "dhaba_tickets.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {t["id"]: t for t in data["tickets"]}

TICKETS = load_all_tickets()

def build_response(ticket: TicketInput) -> TriageResponse:
    # Build a simple successful refund response for testing
    refund = RefundDecision(
        approved=True,
        amount_inr=249,
        reason="Test refund approved",
        payment_id="pay_A2",
    )
    return TriageResponse(
        ticket_id=ticket.id,
        category=TriageCategory.REFUND_REQUEST,
        severity=SeverityLevel.P1_HIGH,
        refund=refund,
        reply_draft="Refund approved",
        needs_human=False,
        confidence=0.99,
    )

def test_idempotent_save_and_get():
    store = IdempotencyStore(db_path=":memory:")
    ticket = TicketInput.model_validate(TICKETS["T-1001"])
    payload = ticket.model_dump()
    payload_hash = IdempotencyStore._hash_payload(payload)
    response = build_response(ticket)

    # First save should insert
    inserted = store.save_result(ticket.id, payload_hash, response)
    assert inserted is True

    # Second save with same hash should be idempotent (no new insert)
    inserted_again = store.save_result(ticket.id, payload_hash, response)
    assert inserted_again is False

    # Retrieval should return the same response
    cached = store.get_existing(ticket.id, payload_hash)
    assert cached is not None
    assert cached.model_dump() == response.model_dump()

def test_conflict_error_on_modified_payload():
    store = IdempotencyStore(db_path=":memory:")
    ticket = TicketInput.model_validate(TICKETS["T-1001"])
    payload = ticket.model_dump()
    payload_hash = IdempotencyStore._hash_payload(payload)
    response = build_response(ticket)
    store.save_result(ticket.id, payload_hash, response)

    # Modify payload (e.g., change body)
    modified = dict(payload)
    modified["body"] = modified["body"] + " extra"
    modified_hash = IdempotencyStore._hash_payload(modified)

    with pytest.raises(IdempotencyConflictError):
        store.get_existing(ticket.id, modified_hash)
