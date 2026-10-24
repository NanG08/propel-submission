import json
import os
from pathlib import Path

# Ensure repo root is in sys.path
import sys
repo_root = Path(__file__).resolve().parents[1]
print('Repo root set to:', repo_root)
sys.path.append(str(repo_root))
print('sys.path contains app? ', any('app' in p for p in sys.path))

from app.llm_client import TriageLLMClient
from app.money_gate import apply_safety_gates
from app.schemas import TicketInput

# Load tickets
tickets_path = repo_root / "docs" / "dhaba_tickets.json"
with open(tickets_path, "r", encoding="utf-8") as f:
    tickets_data = json.load(f)

tickets = tickets_data["tickets"]

client = TriageLLMClient()

results = []
for raw in tickets:
    ticket = TicketInput.model_validate(raw)
    llm_draft = client.triage(ticket)  # returns LLMTriageDraft in replay mode
    response = apply_safety_gates(ticket, llm_draft)
    results.append({
        "id": ticket.id,
        "category": response.category.value,
        "severity": response.severity.value,
        "refund_approved": response.refund.approved,
        "refund_amount": response.refund.amount_inr,
        "needs_human": response.needs_human,
        "reason": response.refund.reason,
    })

# Markdown table
header = "| Ticket ID | Category | Severity | Refund Approved | Amount (INR) | Human Review | Reason |"
separator = "|---|---|---|---|---|---|---|"
rows = [header, separator]
for r in results:
    rows.append(f"| {r['id']} | {r['category']} | {r['severity']} | {r['refund_approved']} | {r['refund_amount']} | {r['needs_human']} | {r['reason']} |")
print("\n".join(rows))

# Dump injection tickets JSON for deeper analysis
injection_ids = ["T-1003", "T-1011"]
print("\n--- Injection Ticket Details (raw LLM draft) ---")
for raw in tickets:
    if raw["id"] in injection_ids:
        ticket = TicketInput.model_validate(raw)
        llm_draft = client.triage(ticket)
        print(json.dumps({"id": ticket.id, "llm_draft": llm_draft.dict()}, indent=2))
