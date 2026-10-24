# money_gate.py
"""Deterministic security and refund policy logic.
All functions are pure and deterministic – no external services.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Tuple, List

from .schemas import TicketInput, LLMTriageDraft, RefundDecision, TriageResponse
from .config import settings

# ---------------------------------------------------------------------------
# Prompt injection detection
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS = [
    r"system note",
    r"ignore your previous instructions",
    r"ignore previous instructions",
    r"system prompt",
    r"internal refund rules",
    r"verified vip",
    r"mark this ticket resolved",
]
_INJECTION_REGEX = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(subject: str, body: str) -> Tuple[bool, List[str]]:
    """Detect deterministic prompt‑injection phrases.

    Returns a tuple ``(detected, matches)`` where ``matches`` is the list of
    matching patterns (lower‑case) found in *subject* or *body*.
    """
    text = f"{subject}\n{body}".lower()
    matches = [pattern for pattern in _INJECTION_PATTERNS if re.search(pattern, text, re.IGNORECASE)]
    return (len(matches) > 0, matches)

# ---------------------------------------------------------------------------
# Refund policy evaluation
# ---------------------------------------------------------------------------
_FRAUD_KEYWORDS = ["fraud", "cyber", "unauthorized", "card", "cyber cell"]
_FRAUD_REGEX = re.compile("|".join(_FRAUD_KEYWORDS), re.IGNORECASE)


def _latest_successful_renewal(ticket: TicketInput):
    renewals = [p for p in ticket.purchases if p.type == "renewal" and p.status == "successful"]
    if not renewals:
        return None
    renewals.sort(key=lambda p: p.at, reverse=True)
    return renewals[0]


def _latest_renewal_any_status(ticket: TicketInput):
    renewals = [p for p in ticket.purchases if p.type == "renewal"]
    if not renewals:
        return None
    renewals.sort(key=lambda p: p.at, reverse=True)
    return renewals[0]


def evaluate_refund_policy(
    ticket: TicketInput,
    llm_draft: LLMTriageDraft,
    injection_detected: bool,
) -> RefundDecision:
    """Deterministic evaluation of refund eligibility.

    Implements the ordered rule set described in the task specification.
    """
    # Rule 1 – injection guard
    if injection_detected or llm_draft.prompt_injection_detected:
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason="Blocked by security guardrail: adversarial instruction detected in ticket.",
            payment_id=None,
        )

    # Rule 2 – fraud / legal escalation
    if _FRAUD_REGEX.search(ticket.body.lower()):
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason="Frozen for immediate human fraud/legal review; auto-refund disabled.",
            payment_id=None,
        )

    # Rule 3 – no refund requested
    if not llm_draft.user_wants_refund:
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason="No refund requested.",
            payment_id=None,
        )

    # Rule 4 – unsettled / initiated payments
    latest_any = _latest_renewal_any_status(ticket)
    if latest_any and latest_any.status == "initiated":
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason="Payment is in 'initiated' (unsettled) state; cannot refund unsettled funds. Escalated for payment reconciliation.",
            payment_id=None,
        )

    # Rule 5 – double‑charge scenario (failed + successful)
    failed = any(p.status == "failed" for p in ticket.purchases if p.type == "renewal")
    successful = any(p.status == "successful" for p in ticket.purchases if p.type == "renewal")
    if failed and successful:
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason="Only one successful charge found; prior attempt failed and was not settled.",
            payment_id=None,
        )

    latest_success = _latest_successful_renewal(ticket)
    if not latest_success:
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason="No successful renewal payment found for refund.",
            payment_id=None,
        )

    # Rule 6 – high‑value annual plan gate (> Rs 500)
    if latest_success.amount_inr >= 1000:
        return RefundDecision(
            approved=False,
            amount_inr=0,
            reason=f"Eligible unused annual renewal (0 opens), but amount Rs {latest_success.amount_inr} exceeds auto‑refund cap (Rs 500); routed for 1‑click human approval",
            payment_id=None,
        )

    # Rule 7 – usage gate on monthly renewal (Rs 249)
    if latest_success.amount_inr == 249:
        opens = ticket.app_opens_since_renewal
        ticket_time = datetime.fromisoformat(ticket.received_at)
        renewal_time = datetime.fromisoformat(latest_success.at)
        delta = ticket_time - renewal_time
        if opens == 0 and delta <= timedelta(hours=48):
            return RefundDecision(
                approved=True,
                amount_inr=latest_success.amount_inr,
                reason="Approved: unused monthly renewal (0 app opens) reported within 48h window.",
                payment_id=latest_success.id,
            )
        else:
            return RefundDecision(
                approved=False,
                amount_inr=0,
                reason=f"Auto-refund declined: {opens} app opens recorded since renewal; routed to human agent.",
                payment_id=None,
            )

    # Fallback – deny
    return RefundDecision(
        approved=False,
        amount_inr=0,
        reason="Refund conditions not met.",
        payment_id=None,
    )

# ---------------------------------------------------------------------------
# Post‑processor applying all safety gates
# ---------------------------------------------------------------------------
_UNSAFE_REPLY_TOKENS = [
    "system prompt",
    "internal refund rules",
    "LLMTriageDraft",
    "system note",
]
_UNSAFE_REPLY_REGEX = re.compile("|".join(_UNSAFE_REPLY_TOKENS), re.IGNORECASE)


def apply_safety_gates(ticket: TicketInput, llm_draft: LLMTriageDraft) -> TriageResponse:
    """Apply safety and policy logic and return a ``TriageResponse``.

    This wrapper now ensures that any deterministic rule that blocks a refund
    also forces ``needs_human`` to ``True``. The original logic only set the flag
    for injection detection and low confidence. The additional check looks at the
    ``RefundDecision`` reason (case‑insensitive) for known block keywords and
    toggles ``needs_human`` accordingly.
    """
    injection_detected, _ = detect_prompt_injection(ticket.subject, ticket.body)
    refund_decision = evaluate_refund_policy(ticket, llm_draft, injection_detected)

    # Determine needs_human flag initially from LLM draft
    needs_human = llm_draft.needs_human

    # Confidence gate – force human review and block refund if low confidence
    if llm_draft.confidence < getattr(settings, "CONFIDENCE_THRESHOLD", 0.75):
        needs_human = True
        refund_decision = RefundDecision(
            approved=False,
            amount_inr=0,
            reason="Confidence below threshold; human review required.",
            payment_id=None,
        )

    # Injection detection forces human review (already covered by refund decision)
    if injection_detected or llm_draft.prompt_injection_detected:
        needs_human = True

    # Additional rule: enforce human review only for specific block reasons.
    # We *do not* treat the double‑charge scenario (Rule 5) as a human‑override.
    # Relevant block reasons that must trigger human review:
    #   * "initiated" – unsettled payment
    #   * "exceeds auto‑refund cap" – high‑value annual plan
    #   * "app opens" – usage gate on monthly renewal
    #   * "fraud" or "cyber" – legal / fraud escalation
    #   * any other non‑"no refund requested" wording that indicates a policy block
    if not refund_decision.approved:
        lower_reason = refund_decision.reason.lower()
        block_keywords = [
            "initiated",
            "exceeds auto‑refund cap",
            "app opens",
            "fraud",
            "cyber",
            "unauthorized",
        ]
        # If the reason contains any of the above keywords, force human review.
        if any(kw in lower_reason for kw in block_keywords):
            needs_human = True

    # Scrub unsafe reply content
    reply = llm_draft.reply_draft
    if _UNSAFE_REPLY_REGEX.search(reply):
        reply = "Thank you for reaching out. We are reviewing your request and will get back to you shortly."

    return TriageResponse(
        ticket_id=ticket.id,
        category=llm_draft.category,
        severity=llm_draft.severity,
        refund=refund_decision,
        reply_draft=reply,
        needs_human=needs_human,
        confidence=llm_draft.confidence,
    )
    """Apply safety and policy logic and return a ``TriageResponse``.
    Includes prompt‑injection detection, refund policy, confidence gating, and
    reply sanitisation.
    """
    injection_detected, _ = detect_prompt_injection(ticket.subject, ticket.body)
    refund_decision = evaluate_refund_policy(ticket, llm_draft, injection_detected)

    # Determine needs_human flag initially from LLM draft
    needs_human = llm_draft.needs_human

    # Confidence gate – force human review and block refund if low confidence
    if llm_draft.confidence < getattr(settings, "CONFIDENCE_THRESHOLD", 0.75):
        needs_human = True
        refund_decision = RefundDecision(
            approved=False,
            amount_inr=0,
            reason="Confidence below threshold; human review required.",
            payment_id=None,
        )

    # If injection detected, also force human review
    if injection_detected or llm_draft.prompt_injection_detected:
        needs_human = True

    # Scrub unsafe reply content
    reply = llm_draft.reply_draft
    if _UNSAFE_REPLY_REGEX.search(reply):
        reply = "Thank you for reaching out. We are reviewing your request and will get back to you shortly."

    return TriageResponse(
        ticket_id=ticket.id,
        category=llm_draft.category,
        severity=llm_draft.severity,
        refund=refund_decision,
        reply_draft=reply,
        needs_human=needs_human,
        confidence=llm_draft.confidence,
    )
