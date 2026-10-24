# logger.py
"""Structured JSON logger with PII scrubbing.
The logger emits JSON lines; a custom filter redacts sensitive patterns.
"""

import logging
import json
import re
from typing import Any, Mapping

# Regex patterns for PII
_GSTIN_REGEX = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b")
_EMAIL_UPI_REGEX = re.compile(r"[\w.+-]+@[\w.-]+|\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b", re.IGNORECASE)
# 10-16 digit numbers (phone/card)
_NUMBER_REGEX = re.compile(r"\b\d{10,16}\b")
# Simple entity redaction (example: Acme Interiors)
_ENTITY_REGEX = re.compile(r"Acme Interiors", re.IGNORECASE)

class PIIScrubberFilter(logging.Filter):
    """Filter that scrubs PII from log records before they are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub message string
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        # Scrub any extra string attributes
        for key, value in getattr(record, "__dict__", {}).items():
            if isinstance(value, str):
                setattr(record, key, self._scrub(value))
        return True

    def _scrub(self, text: str) -> str:
        text = _GSTIN_REGEX.sub("[REDACTED_GSTIN]", text)
        text = _EMAIL_UPI_REGEX.sub("[REDACTED_EMAIL_UPI]", text)
        text = _NUMBER_REGEX.sub("[REDACTED_NUMBER]", text)
        text = _ENTITY_REGEX.sub("[REDACTED_ENTITY]", text)
        return text

_logger = logging.getLogger("app_logger")
_logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(message)s"))
_handler.addFilter(PIIScrubberFilter())
_logger.addHandler(_handler)
_logger.propagate = False

def log_event(event_type: str, ticket_id: str, **kwargs: Any) -> None:
    """Log a structured JSON event.

    Args:
        event_type: Type of event, e.g., "ticket_received".
        ticket_id: Identifier of the ticket.
        **kwargs: Additional fields (must not include raw ``body`` or ``subject``).
    """
    prohibited = {"body", "subject"}
    bad = prohibited.intersection(kwargs)
    if bad:
        raise ValueError(f"Prohibited raw PII fields passed to log_event: {bad}")
    payload: Mapping[str, Any] = {"event_type": event_type, "ticket_id": ticket_id, **kwargs}
    _logger.info(json.dumps(payload))
