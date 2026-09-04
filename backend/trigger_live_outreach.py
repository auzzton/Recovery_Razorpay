import os
import sys

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(project_root, ".env"))

from backend.app.models import PaymentWebhookPayload
from backend.app.main import ingest_payment_webhook

print("--- DISPATCHING LIVE TEST PAYMENT RECOVERY OUTREACH ---")
print("Target Email: auzton7@gmail.com")
print("Target Phone: +919361001990")

payload = PaymentWebhookPayload(
    merchant_id="merch_live_demo",
    customer_name="Auzton",
    customer_email="auzton7@gmail.com",
    customer_phone="+919361001990",
    customer_tier="STANDARD",
    amount_in_cents=149900,  # ₹1,499.00
    event_type="subscription.charged",
    failure_code="CARD_EXPIRED",
    razorpay_payment_id="pay_LIVE_DEMO_990"
)

res = ingest_payment_webhook(payload)

print("\n--- DISPATCH RESULT ---")
print("Status:", res.get("status"))
print("Event ID:", res.get("event_id"))
print("Triage Recommended Action:", res.get("triage_action"))
print("FSM State:", res.get("fsm_state"))
print("Outreach Dispatch Result:", res.get("outreach_result"))
