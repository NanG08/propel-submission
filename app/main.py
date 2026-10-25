"""FastAPI entry point for the Dhaba Ticket Triage service.

This module wires together:
* Request validation via ``TicketInput`` (pydantic models).
* Idempotency handling backed by SQLite (``IdempotencyStore``).
* LLM triage client (``TriageLLMClient``) – works in *replay* mode when no API key is set.
* Deterministic money‑gate logic (``apply_safety_gates``).
* Minimal logging (PII‑scrubbed).

The public API consists of two endpoints:
* ``POST /triage`` – full end‑to‑end processing of a ticket.
* ``GET /health`` – health check that reports the current ``TRIAGE_MODE``.
"""

from fastapi import FastAPI, Header, HTTPException, Response, status
import hashlib
import json
import os
import logging

from .schemas import TicketInput, TriageResponse
from .idempotency import IdempotencyStore, IdempotencyConflictError
from .llm_client import TriageLLMClient
from .money_gate import apply_safety_gates
from .logger import get_logger

# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Dhaba Ticket Triage", version="1.0.0")
logger = get_logger(__name__)

# Ensure the SQLite DB exists – the store will create the file on first use.
_store = IdempotencyStore()
_llm_client = TriageLLMClient()

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _canonical_hash(ticket: TicketInput) -> str:
    """Return a SHA‑256 hash of the *canonical* JSON representation of a ticket.

    The canonical form is produced by ``json.dumps`` with ``sort_keys=True`` and
    ``separators=(',', ':')`` to remove whitespace differences.
    """
    canonical = json.dumps(ticket.dict(), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    """Simple health probe.

    Returns a JSON object with ``status`` always ``"ok"`` and the current
    ``TRIAGE_MODE`` (``"replay"`` or ``"live"``).  No external calls are made.
    """
    mode = os.getenv("TRIAGE_MODE", "replay")
    logger.info("Health check – mode=%s", mode)
    return {"status": "ok", "mode": mode}


@app.post("/triage", response_model=TriageResponse)
def triage_endpoint(
    ticket: TicketInput,
    response: Response,
    x_idempotent_replay: str = Header(None),  # client‑side header echo – not used
) -> TriageResponse:
    """Process a ticket and return a ``TriageResponse``.

    The flow follows the specification from STEP 5:
    1. Compute a canonical payload hash.
    2. Look up a cached result in ``IdempotencyStore``.
       * Hit → return cached response with ``X‑Idempotent‑Replay: true``.
       * Conflict → raise ``HTTPException`` 409.
    3. Call the LLM client (replay or live).
    4. Run deterministic safety gates.
    5. Persist the final response.
    6. Return the response with ``X‑Idempotent‑Replay: false``.
    """
    payload_hash = _canonical_hash(ticket)
    logger.debug("Payload hash for ticket %s: %s", ticket.id, payload_hash)

    try:
        cached = _store.get_existing(ticket.id, payload_hash)
        if cached:
            logger.info("Idempotent replay hit for ticket %s", ticket.id)
            response.headers["X-Idempotent-Replay"] = "true"
            return cached
    except IdempotencyConflictError as e:
        logger.warning(
            "Idempotency conflict for ticket %s: %s", ticket.id, str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency conflict: payload differs from stored ticket.",
        ) from e

    logger.info(
        "Processing new ticket %s (mode=%s)",
        ticket.id,
        os.getenv("TRIAGE_MODE", "replay"),
    )
    llm_draft = _llm_client.triage(ticket)
    final_response = apply_safety_gates(ticket, llm_draft)

    saved = _store.save_result(ticket.id, payload_hash, final_response)
    if not saved:
        logger.info("Concurrent insert detected – treating as replay for %s", ticket.id)
        response.headers["X-Idempotent-Replay"] = "true"
    else:
        response.headers["X-Idempotent‑Replay"] = "false"

    logger.info(
        "Finished processing ticket %s – refund approved=%s, needs_human=%s",
        ticket.id,
        final_response.refund.approved,
        final_response.needs_human,
    )
    return final_response