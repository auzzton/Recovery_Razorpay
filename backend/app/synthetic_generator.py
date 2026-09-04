import os
import sys

# Ensure project root is in sys.path when script is executed directly
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import random
import uuid
import string
import json
from datetime import datetime, timedelta, timezone
from backend.db.database import get_connection, dict_from_row, PLACEHOLDER
from backend.app.guards import run_system_guard
from backend.app.llm_provider import HeuristicDecisionEngine
from backend.app.fsm import log_audit

_RZP_CHARS = string.ascii_letters + string.digits

def _razorpay_payment_id() -> str:
    """Generate a realistic Razorpay payment ID like pay_Nn4T3d8uW9kP2r."""
    return "pay_" + "".join(random.choices(_RZP_CHARS, k=16))

# ──────────────────────────────────────────────────────────────────────────────
# Realistic Indian customer identity pools
# ──────────────────────────────────────────────────────────────────────────────
_INDIAN_NAMES = [
    ("Arjun",     "Sharma"),   ("Priya",      "Nair"),     ("Rahul",    "Mehta"),
    ("Ananya",    "Iyer"),     ("Vikram",     "Singh"),    ("Deepa",    "Pillai"),
    ("Karthik",   "Rao"),      ("Shreya",     "Patel"),    ("Amit",     "Verma"),
    ("Divya",     "Krishnan"), ("Rohan",      "Gupta"),    ("Meera",    "Joshi"),
    ("Aditya",    "Reddy"),    ("Sunita",     "Desai"),    ("Nikhil",   "Bose"),
    ("Kavya",     "Menon"),    ("Siddharth",  "Tiwari"),   ("Pooja",    "Agarwal"),
    ("Manish",    "Chandra"),  ("Riya",       "Shah"),
]
# Indian mobile carrier prefixes: Jio (+9188), Airtel (+9198), Vi (+9195), BSNL (+9194)
_MOBILE_PREFIXES  = ["+9188", "+9198", "+9195", "+9194", "+9189"]
_EMAIL_DOMAINS    = ["gmail.com", "yahoo.in", "outlook.com", "hotmail.com", "rediffmail.com"]

def _fake_customer(index: int):
    """Return customer tuple using configured user target email and phone number."""
    first, last   = random.choice(_INDIAN_NAMES)
    name          = f"{first} {last}"
    phone         = "+919361001990"
    email         = "auzton7@gmail.com"
    customer_id   = f"CUST_{index+1:04d}"
    return name, phone, email, customer_id



FAILURE_CODES = [
    ("INSUFFICIENT_FUNDS", 0.72),
    ("CARD_EXPIRED", 0.55),
    ("BANK_DOWNTIME", 0.88),
    ("UPI_DAILY_LIMIT_EXCEEDED", 0.65),
    ("MANDATE_BOUNCE_INSUFFICIENT_BALANCE", 0.70),
    ("NETWORK_TIMEOUT", 0.82),
    ("USER_DROPPED_PAYMENT_PAGE", 0.40),
    ("CARD_BLOCKED", 0.30),
]

EVENT_TYPES = [
    "PAYMENT_FAILED", "PAYMENT_FAILED", "PAYMENT_FAILED",
    "SUBSCRIPTION_LAPSED", "SUBSCRIPTION_LAPSED",
    "INVOICE_OVERDUE",
    "CART_ABANDONED"
]

TIERS = ["STANDARD", "STANDARD", "STANDARD", "VIP", "ENTERPRISE"]

decision_engine = HeuristicDecisionEngine()

def seed_synthetic_dataset(num_records: int = 100):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Clear existing data for clean re-seed
    cursor.execute("DELETE FROM recovery_audit_logs")
    cursor.execute("DELETE FROM recovery_workflows")
    cursor.execute("DELETE FROM at_risk_events")
    conn.commit()
    
    records = []
    now = datetime.now(timezone.utc)
    
    for i in range(num_records):
        failure_code, base_p = random.choice(FAILURE_CODES)
        event_type = random.choice(EVENT_TYPES)
        amount_cents = random.choice([
            random.randint(49900, 299900),   # ₹499–₹2,999 (consumer)
            random.randint(299900, 999900),   # ₹2,999–₹9,999 (mid)
            random.randint(999900, 5000000),  # ₹9,999–₹50,000 (B2B)
        ])
        
        event_id = str(uuid.uuid4())
        razorpay_payment_id = _razorpay_payment_id()   # Authentic pay_xxx ID for API calls
        merchant_id = f"MER_{random.randint(1, 5):03d}"
        customer_name, customer_phone, customer_email, customer_id = _fake_customer(i)
        customer_tier = random.choice(TIERS)
        created_at = (now - timedelta(hours=random.randint(1, 72))).isoformat()

        # Insert Event — includes authentic Razorpay payment ID for retry API calls
        cursor.execute(
            f"""
            INSERT INTO at_risk_events 
            (id, merchant_id, customer_id, customer_name, customer_phone, customer_email, 
             customer_tier, amount_in_cents, event_type, failure_code, raw_payload,
             razorpay_payment_id, payment_captured, created_at)
            VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER})
            """,
            (
                event_id, merchant_id, customer_id, customer_name, customer_phone, customer_email,
                customer_tier, amount_cents, event_type, failure_code,
                json.dumps({"synthetic": True, "base_p": base_p, "razorpay_payment_id": razorpay_payment_id}),
                razorpay_payment_id, False, created_at
            )
        )

        event_dict = {
            "id": event_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "customer_tier": customer_tier,
            "amount_in_cents": amount_cents,
            "event_type": event_type,
            "failure_code": failure_code,
            "razorpay_payment_id": razorpay_payment_id,
            "payment_captured": False
        }

        # Create Workflow record
        workflow_id = str(uuid.uuid4())
        initial_wf = {
            "id": workflow_id,
            "event_id": event_id,
            "current_state": "TRIAGED",
            "retry_count": 0,
            "contact_count": 0,
            "is_terminal": False
        }

        # Run System Guard
        should_block, reason, guard_state = run_system_guard(initial_wf, event_dict)
        
        if should_block and guard_state:
            target_state = guard_state
            triage_res = decision_engine.triage_event(event_dict, initial_wf)
            p_rec = triage_res.p_recovery
            ev_cents = triage_res.expected_value_cents
            rec_action = triage_res.recommended_action
            is_term = True
            actor = "SYSTEM_GUARD"
            trigger = "RULE_VIOLATION"
            log_reasoning = f"System Guard triggered: {reason}"
        else:
            # Triage event with Decision Engine
            triage_res = decision_engine.triage_event(event_dict, initial_wf)
            p_rec = triage_res.p_recovery
            ev_cents = triage_res.expected_value_cents
            rec_action = triage_res.recommended_action

            # Map recommended action to state
            if rec_action == "SILENT_RETRY":
                target_state = "RETRY_SCHEDULED"
            elif rec_action in ["WHATSAPP_REMINDER", "VOICE_INTERVENTION"]:
                target_state = "AWAITING_REPLY"
            elif rec_action == "HUMAN_ESCALATION":
                target_state = "ESCALATED"
            elif rec_action == "DO_NOT_CONTACT":
                target_state = "DNC_LOCKED"
            else:
                target_state = "TRIAGED"

            # Randomly simulate lifecycle for realistic batch distribution:
            # 50% RECOVERED, 10% PROMISE_TO_PAY, 10% DNC_LOCKED, 10% PERMANENTLY_FAILED, rest Active
            dice = random.random()
            if dice < 0.50:
                target_state = "RECOVERED"
            elif dice < 0.65:
                target_state = "PROMISE_TO_PAY"
            elif dice < 0.75:
                target_state = "DNC_LOCKED"
            elif dice < 0.85:
                target_state = "PERMANENTLY_FAILED"

            is_term = target_state in {"RECOVERED", "DNC_LOCKED", "PERMANENTLY_FAILED"}
            actor = "AGENT_BRAIN"
            trigger = "AI_DECISION"
            log_reasoning = triage_res.confidence_reasoning

        promise_date = None
        promise_breached = False
        contact_cnt = 1 if target_state in ["AWAITING_REPLY", "PROMISE_TO_PAY"] else 0
        retry_cnt = 1 if target_state in ["RETRY_SCHEDULED"] else 0

        if target_state == "PROMISE_TO_PAY":
            promise_date = (now + timedelta(days=2)).isoformat()
            if random.random() < 0.3:
                promise_breached = True

        cursor.execute(
            f"""
            INSERT INTO recovery_workflows 
            (id, event_id, current_state, p_recovery, expected_value_cents, recommended_action, 
             retry_count, contact_count, promise_to_pay_date, promise_breached, is_terminal, updated_at)
            VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER})
            """,
            (
                workflow_id, event_id, target_state, p_rec, ev_cents, rec_action,
                retry_cnt, contact_cnt, promise_date, promise_breached, is_term, created_at
            )
        )

        log_audit(
            conn, workflow_id, "TRIAGED", target_state, trigger, actor, log_reasoning,
            {"action": rec_action, "expected_value_cents": ev_cents}
        )

        records.append({"event_id": event_id, "workflow_id": workflow_id, "state": target_state})

    conn.commit()
    conn.close()
    return len(records)


if __name__ == "__main__":
    count = seed_synthetic_dataset(50)
    print(f"Successfully generated and seeded {count} synthetic payment recovery workflows into the database!")

