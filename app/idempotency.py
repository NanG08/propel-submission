# idempotency.py
"""SQLite‑backed idempotency store for triage responses.
All operations are atomic and safe for concurrent usage.
"""

from __future__ import annotations

import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional

from .config import settings
from .schemas import TriageResponse

class IdempotencyConflictError(Exception):
    """Raised when a ticket is re‑submitted with a different payload hash.
    The API layer can translate this to HTTP 409 Conflict.
    """

class IdempotencyStore:
    """Simple SQLite store that guarantees at‑most‑once processing per ticket.

    The table ``triage_ledger`` records the hash of the request payload and the
    serialized ``TriageResponse``.  ``INSERT OR IGNORE`` ensures that duplicate
    submissions with the same hash are idempotent, while a mismatch triggers a
    conflict error.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.DB_PATH
        # ``detect_types`` enables parsing of dates if needed (not used here).
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_ledger (
                ticket_id TEXT PRIMARY KEY,
                payload_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                refund_approved INTEGER NOT NULL,
                refund_amount_inr INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        """Return a SHA‑256 hex digest of a canonical JSON representation.
        The dict is first dumped with ``sort_keys`` to guarantee determinism.
        """
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get_existing(self, ticket_id: str, payload_hash: str) -> Optional[TriageResponse]:
        """Return a cached ``TriageResponse`` if the ``ticket_id`` exists.

        * If the stored hash matches ``payload_hash`` – the cached response is
          returned.
        * If the stored hash differs – ``IdempotencyConflictError`` is raised.
        * If no row exists – ``None`` is returned.
        """
        cur = self.conn.execute(
            "SELECT payload_hash, response_json FROM triage_ledger WHERE ticket_id = ?",
            (ticket_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        stored_hash, response_json = row
        if stored_hash != payload_hash:
            raise IdempotencyConflictError(
                f"Ticket '{ticket_id}' already processed with a different payload."
            )
        data = json.loads(response_json)
        return TriageResponse.model_validate(data)

    def save_result(self, ticket_id: str, payload_hash: str, response: TriageResponse) -> bool:
        """Persist ``response`` for ``ticket_id``.

        Returns ``True`` if the row was inserted (i.e., first time), ``False`` if
        an identical row already existed (idempotent call).
        """
        response_json = response.model_dump_json()
        refund_approved = 1 if response.refund.approved else 0
        refund_amount = response.refund.amount_inr
        created_at = datetime.utcnow().isoformat()
        before = self.conn.total_changes
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO triage_ledger (
                    ticket_id, payload_hash, response_json,
                    refund_approved, refund_amount_inr, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    payload_hash,
                    response_json,
                    refund_approved,
                    refund_amount,
                    created_at,
                ),
            )
        after = self.conn.total_changes
        return after > before
