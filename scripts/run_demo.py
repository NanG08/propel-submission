import os
import json
from app.llm_client import TriageLLMClient
from app.schemas import TicketInput

# Load sample ticket (T-1001) from fixtures
tickets_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'dhaba_tickets.json')
with open(tickets_path, 'r', encoding='utf-8') as f:
    tickets = json.load(f)

ticket_data = next(
    t for t in tickets["tickets"] if t.get("id") == "T-1001"
)
ticket = TicketInput.model_validate(ticket_data)

# Ensure replay mode (no API key needed)
os.environ.setdefault('TRIAGE_MODE', 'replay')

client = TriageLLMClient()
llm_draft = client.triage(ticket)
print('LLM Draft:', llm_draft)
