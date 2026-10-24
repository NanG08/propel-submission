# llm_client.py
"""Simple deterministic LLM client used in *replay* mode.
The real project would call Gemini/OpenAI, but for the purpose of
documentation we need a deterministic client that returns the canned
responses stored in ``app/fixtures/replay_responses.json``.
"""

import json
from pathlib import Path
from typing import Any

from .schemas import LLMTriageDraft, TriageCategory, SeverityLevel

class TriageLLMClient:
    """Load pre‑recorded LLM drafts from the fixture file.

    The fixture contains a mapping of ticket IDs to a dict with the
    fields required by :class:`LLMTriageDraft`.  If a ticket ID is not
    present we fall back to a generic ``REFUND_REQUEST`` draft with a
    high confidence score – this mirrors the behaviour of the original
    implementation in replay mode.
    """

    def __init__(self) -> None:
        fixtures_path = Path(__file__).parent / "fixtures" / "replay_responses.json"
        if fixtures_path.is_file():
            with fixtures_path.open("r", encoding="utf-8") as f:
                self._data: dict[str, Any] = json.load(f)
        else:
            self._data = {}

    def _draft_from_dict(self, d: dict[str, Any]) -> LLMTriageDraft:
        # Convert string enums to the proper Enum classes expected by the model.
        return LLMTriageDraft(
            category=TriageCategory(d["category"]),
            severity=SeverityLevel(d["severity"]),
            user_wants_refund=d.get("user_wants_refund", False),
            reply_draft=d.get("reply_draft", ""),
            needs_human=d.get("needs_human", False),
            confidence=d.get("confidence", 1.0),
            prompt_injection_detected=d.get("prompt_injection_detected", False),
            reasoning=d.get("reasoning", ""),
        )

    def triage(self, ticket) -> LLMTriageDraft:
        """Return the deterministic draft for *ticket*.

        ``ticket`` is an instance of :class:`app.schemas.TicketInput`.
        The method first looks up ``ticket.id`` in the fixture.  If the
        ID is missing a generic fallback draft is returned.
        """
        raw = self._data.get(ticket.id)
        if raw:
            return self._draft_from_dict(raw)
        # Fallback – a safe default that triggers no refund.
        return LLMTriageDraft(
            category=TriageCategory.REFUND_REQUEST,
            severity=SeverityLevel.P3_LOW,
            user_wants_refund=False,
            reply_draft="",
            needs_human=False,
            confidence=1.0,
            prompt_injection_detected=False,
            reasoning="",
        )
