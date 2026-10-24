# tests/test_step1_foundation.py
"""Step 1 foundation tests.
- Validate all tickets from dhaba_tickets.json parse into TicketInput.
- Ensure Pydantic validation errors are raised for invalid enum values and negative numbers.
- Verify the logger redacts GSTIN and entity names.
"""

import json
import logging
from pathlib import Path

import pytest
from app.schemas import TicketInput, TriageCategory, SeverityLevel, RefundDecision
from app.logger import log_event

# Helper to load tickets JSON
def load_tickets() -> list[dict]:
    # The JSON file lives in ../docs relative to this test file.
    json_path = Path(__file__).parent.parent / "docs" / "dhaba_tickets.json"
    if not json_path.is_file():
        # When tests are run from the project root, the path is simpler.
        json_path = Path(__file__).parents[2] / "propel-dhaba-submission" / "docs" / "dhaba_tickets.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["tickets"]


def test_all_tickets_parse():
    tickets = load_tickets()
    assert len(tickets) == 12
    for raw in tickets:
        ti = TicketInput.model_validate(raw)
        assert ti.id.startswith("T-")
        for p in ti.purchases:
            assert p.amount_inr >= 0


def test_invalid_enum_and_negative_refund():
    with pytest.raises(ValueError):
        TriageCategory("INVALID_CATEGORY")
    with pytest.raises(ValueError):
        SeverityLevel("P4_UNKNOWN")
    with pytest.raises(ValueError):
        RefundDecision(approved=True, amount_inr=-5, reason="test")


def test_logger_redacts_pii(caplog):
    caplog.set_level(logging.INFO, logger="app_logger")
    raw_message = "Invoice for Acme Interiors, GSTIN 29ABCDE1234F1Z5"
    # Pass the raw message via an allowed extra field (not prohibited)
    log_event("test_event", "T-1010", details=raw_message)
    # Ensure at least one record was captured
    assert caplog.records, "No log records captured"
    # The logger emits a single JSON line string
    json_line = caplog.records[-1].message
    assert "[REDACTED_GSTIN]" in json_line
    assert "[REDACTED_ENTITY]" in json_line
    assert "29ABCDE1234F1Z5" not in json_line
    assert "Acme Interiors" not in json_line
