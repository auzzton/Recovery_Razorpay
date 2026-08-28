import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Adjust python path to find backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.database import get_connection, init_db, dict_from_row, DB_BACKEND, SCHEMA_PATH
from backend.app.date_parser import extract_promise_date, get_promise_date
from backend.app.main import check_and_trigger_breaches
from backend.app.fsm import transition_state

class TestRecoveryOSFixes(unittest.TestCase):

    def setUp(self):
        # Ensure database is clean or re-initialized before tests
        init_db()
        # Clean all tables to prevent test state leakages across test runs
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recovery_audit_logs")
        cursor.execute("DELETE FROM recovery_workflows")
        cursor.execute("DELETE FROM at_risk_events")
        conn.commit()
        conn.close()


    def test_date_parser_nlp(self):
        print("\n--- Running Date Parser NLP Tests ---")
        
        # Test 1: Pay on Friday
        date_friday = extract_promise_date("Pay on Friday")
        self.assertIsNotNone(date_friday)
        print(f"Parsed 'Pay on Friday' -> {date_friday}")
        # Friday should be in the future
        self.assertTrue(date_friday > datetime.now(timezone.utc))

        # Test 2: Tomorrow at 5pm
        date_tomorrow = extract_promise_date("will pay tomorrow at 5pm")
        self.assertIsNotNone(date_tomorrow)
        print(f"Parsed 'will pay tomorrow at 5pm' -> {date_tomorrow}")
        self.assertTrue(date_tomorrow > datetime.now(timezone.utc))

        # Test 3: Standard fallback for messages without dates
        fallback = get_promise_date("I am busy")
        fallback_dt = datetime.fromisoformat(fallback)
        expected_fallback = datetime.now(timezone.utc) + timedelta(days=3)
        # Difference should be less than 5 seconds
        self.assertLess(abs((fallback_dt - expected_fallback).total_seconds()), 5)
        print(f"Parsed 'I am busy' (fallback) -> {fallback}")

    def test_postgres_schema_compatibility(self):
        print("\n--- Running Database Schema & Query Tests ---")
        print(f"    [DB_BACKEND = {DB_BACKEND}]")

        # ── 1. Verify schema.sql literally contains SERIAL PRIMARY KEY ─────────
        # This is the canonical truth regardless of which backend is active.
        with open(SCHEMA_PATH, "r") as f:
            raw_schema = f.read()
        self.assertIn(
            "SERIAL PRIMARY KEY", raw_schema.upper(),
            "schema.sql must define recovery_audit_logs.id as SERIAL PRIMARY KEY "
            "(the canonical PostgreSQL definition)."
        )
        print("    schema.sql contains 'SERIAL PRIMARY KEY' — canonical Postgres definition confirmed.")

        # ── 2. Confirm the active DB backend ──────────────────────────────────
        if DB_BACKEND == "postgresql":
            print("    Running against REAL PostgreSQL (DATABASE_URL is set).")
        else:
            print("    Running against SQLite (DATABASE_URL not set). "
                  "SERIAL was rewritten to INTEGER at load time — "
                  "set DATABASE_URL to test against real Postgres.")

        # ── 3. Exercise the audit log table on whichever backend is active ─────
        # Use the correct placeholder: ? for SQLite, %s for psycopg2
        ph = "%s" if DB_BACKEND == "postgresql" else "?"

        conn = get_connection()
        try:
            cur = conn.cursor() if DB_BACKEND == "sqlite" else conn.cursor(
                **({"cursor_factory": __import__("psycopg2.extras", fromlist=["RealDictCursor"]).RealDictCursor}
                   if DB_BACKEND == "postgresql" else {})
            )

            # Insert event
            if DB_BACKEND == "postgresql":
                cur.execute(
                    f"""
                    INSERT INTO at_risk_events
                    (id, merchant_id, customer_id, customer_name, customer_phone, customer_email, amount_in_cents, event_type)
                    VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                    ON CONFLICT (id) DO NOTHING
                    """,
                    ('test_event_123','merch_1','cust_1','Test Customer','9999999999','test@test.com',5000,'PAYMENT_FAILED')
                )
                cur.execute(
                    f"""
                    INSERT INTO recovery_workflows
                    (id, event_id, current_state, promise_to_pay_date, promise_breached, is_terminal)
                    VALUES ({ph},{ph},{ph},NULL,false,false)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    ('test_wf_123','test_event_123','TRIAGED')
                )
            else:
                cur.execute(
                    f"""
                    INSERT OR IGNORE INTO at_risk_events
                    (id, merchant_id, customer_id, customer_name, customer_phone, customer_email, amount_in_cents, event_type)
                    VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                    """,
                    ('test_event_123','merch_1','cust_1','Test Customer','9999999999','test@test.com',5000,'PAYMENT_FAILED')
                )
                cur.execute(
                    f"""
                    INSERT OR IGNORE INTO recovery_workflows
                    (id, event_id, current_state, promise_to_pay_date, promise_breached, is_terminal)
                    VALUES ({ph},{ph},{ph},NULL,0,0)
                    """,
                    ('test_wf_123','test_event_123','TRIAGED')
                )

            # Insert audit log — id column is SERIAL on Postgres, INTEGER on SQLite
            if DB_BACKEND == "postgresql":
                cur.execute(
                    f"""
                    INSERT INTO recovery_audit_logs
                    (workflow_id, from_state, to_state, trigger_type, actor, reasoning, created_at)
                    VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})
                    RETURNING id
                    """,
                    ('test_wf_123','TRIAGED','PROMISE_TO_PAY','USER_INPUT','AGENT_BRAIN','Test reasoning',
                     datetime.now(timezone.utc).isoformat())
                )
                log_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    f"""
                    INSERT INTO recovery_audit_logs
                    (workflow_id, from_state, to_state, trigger_type, actor, reasoning, created_at)
                    VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})
                    """,
                    ('test_wf_123','TRIAGED','PROMISE_TO_PAY','USER_INPUT','AGENT_BRAIN','Test reasoning',
                     datetime.now(timezone.utc).isoformat())
                )
                log_id = cur.lastrowid

            self.assertIsNotNone(log_id)
            print(f"    Inserted audit log — auto-generated id={log_id} "
                  f"({'SERIAL on Postgres' if DB_BACKEND == 'postgresql' else 'INTEGER (rewritten from SERIAL) on SQLite'}).")

            # Read back and verify
            cur.execute(f"SELECT * FROM recovery_audit_logs WHERE id = {ph}", (log_id,))
            row = dict_from_row(cur.fetchone())
            self.assertEqual(row["workflow_id"], 'test_wf_123')
            print("    Row read back successfully. Serialisation schema works correctly.")

            conn.commit()
        finally:
            conn.close()

    def test_scheduler_breach_detection(self):
        print("\n--- Running Scheduler Breach Detection Tests ---")
        # Initialize test data
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. Create event
        cursor.execute(
            """
            INSERT OR REPLACE INTO at_risk_events 
            (id, merchant_id, customer_id, customer_name, amount_in_cents, event_type)
            VALUES ('evt_scheduler_test', 'merch_1', 'cust_2', 'Scheduler Test Customer', 10000, 'PAYMENT_FAILED')
            """
        )
        
        # 2. Create workflow with promise_to_pay_date set to 3 hours ago (overdue)
        overdue_promise = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        cursor.execute(
            """
            INSERT OR REPLACE INTO recovery_workflows
            (id, event_id, current_state, promise_to_pay_date, promise_breached, is_terminal)
            VALUES ('wf_scheduler_test', 'evt_scheduler_test', 'PROMISE_TO_PAY', ?, 0, 0)
            """
        , (overdue_promise,))
        conn.commit()
        conn.close()

        # Run scheduler check job
        check_and_trigger_breaches()

        # Verify state transitioned to PROMISE_BREACHED
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT current_state, promise_breached FROM recovery_workflows WHERE id = 'wf_scheduler_test'")
        row = cursor.fetchone()
        conn.close()

        # Now that auto re-triage triggers post-breach, the FSM transitions to RETRY_SCHEDULED
        self.assertEqual(row["current_state"], "RETRY_SCHEDULED")
        self.assertEqual(row["promise_breached"], 1)
        print("Successfully verified background breach job transitions overdue promises automatically and triggers auto re-triage!")


    def test_gemini_decision_engine_fallback_and_config(self):
        print("\n--- Running Gemini Decision Engine Fallback & Config Tests ---")
        from backend.app.llm_provider import GeminiDecisionEngine

        # Test case 1: Verify fallback engine is loaded if API key is absent
        os.environ.pop("GEMINI_API_KEY", None)
        engine = GeminiDecisionEngine()
        self.assertFalse(engine.client_ready)
        
        event = {
            "failure_code": "BANK_DOWNTIME",
            "amount_in_cents": 10000,
            "customer_tier": "VIP"
        }
        workflow_context = {"retry_count": 0, "contact_count": 0}
        
        # Should fallback to heuristic engine successfully
        res = engine.triage_event(event, workflow_context)
        self.assertEqual(res.recommended_action, "SILENT_RETRY")
        print("Successfully verified heuristic fallback for triage when API key is absent.")

        # Test case 2: Model swap flexibility
        os.environ["GEMINI_MODEL"] = "gemini-2.5-flash-lite"
        engine_swap = GeminiDecisionEngine()
        self.assertEqual(engine_swap.model_name, "gemini-2.5-flash-lite")
        print(f"Successfully verified model swap config: {engine_swap.model_name}")

    def test_outreach_dispatcher_simulation_mode(self):
        print("\n--- Running Outreach Dispatcher Simulation Tests ---")
        # Unset all outreach credentials to force simulation mode
        for key in ["RESEND_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
                    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]:
            os.environ.pop(key, None)

        import importlib
        import backend.app.outreach_dispatcher as dispatcher
        importlib.reload(dispatcher)  # reload so env vars take effect

        result = dispatcher.send_payment_reminder(
            customer_name="Test User",
            customer_email=None,       # no email — forces fallback chain
            customer_phone=None,       # no phone — forces simulation
            amount_in_cents=50000,
            failure_code="INSUFFICIENT_FUNDS",
            payment_url="https://rzp.io/l/rec_test",
            message_body="Hi Test User, your payment of ₹500.00 failed.",
            event_id="test_event_dispatch_001",
        )
        self.assertEqual(result["channel"], "SIMULATION")
        self.assertEqual(result["status"], "simulated")
        print(f"Dispatcher simulation mode verified: channel={result['channel']}")

        # With email present, still simulation (no RESEND_API_KEY / SMTP creds)
        result2 = dispatcher.send_payment_reminder(
            customer_name="Test User",
            customer_email="test@example.com",
            customer_phone="+919876543210",
            amount_in_cents=100000,
            failure_code="CARD_EXPIRED",
            payment_url="https://rzp.io/l/rec_test2",
            message_body="Hi Test User, your payment of ₹1000 failed.",
            event_id="test_event_dispatch_002",
        )
        self.assertEqual(result2["channel"], "SIMULATION")
        print(f"Dispatcher with email+phone still simulation (no keys): channel={result2['channel']}")

    def test_webhook_full_pipeline(self):
        print("\n--- Running Full Webhook Pipeline Test ---")
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        # Trigger the automated webhook pipeline
        response = client.post("/api/webhook/razorpay", json={
            "customer_name": "Webhook Test Customer",
            "amount_in_cents": 150000,
            "failure_code": "INSUFFICIENT_FUNDS",
            "customer_email": "webhook_test@example.com",
            "customer_phone": "+919999000001",
            "customer_tier": "VIP",
            "merchant_id": "MER_TEST",
            "event_type": "PAYMENT_FAILED",
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        print(f"Webhook response status: {data['status']}")
        print(f"Event ID: {data['event_id']}")
        print(f"Triage action: {data['triage']['recommended_action']}")
        print(f"FSM state: {data['triage']['fsm_state']}")
        print(f"Outreach channel: {data['outreach']['channel'] if data['outreach'] else 'None (SILENT_RETRY)'}")

        # Assertions
        self.assertEqual(data["status"], "PROCESSED")
        self.assertIn("event_id", data)
        self.assertIn("workflow_id", data)
        self.assertIsNotNone(data["triage"]["recommended_action"])
        self.assertIsNotNone(data["triage"]["fsm_state"])

        # Verify event is persisted in DB
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM at_risk_events WHERE id = ?", (data["event_id"],))
        event_row = cursor.fetchone()
        cursor.execute("SELECT * FROM recovery_workflows WHERE id = ?", (data["workflow_id"],))
        wf_row = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) as cnt FROM recovery_audit_logs WHERE workflow_id = ?", (data["workflow_id"],))
        audit_count = cursor.fetchone()["cnt"]
        conn.close()

        self.assertIsNotNone(event_row)
        self.assertIsNotNone(wf_row)
        self.assertGreater(audit_count, 0)
        print(f"DB verified: event_id={event_row['id']} state={wf_row['current_state']} audit_logs={audit_count}")
        print("Full webhook pipeline test PASSED — event persisted, triage ran, audit logged, outreach dispatched!")

    def test_twilio_webhook_ingestion(self):
        print("\n--- Running Twilio Inbound Webhook Tests ---")
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        # 1. Create a dummy active event and workflow to target
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO at_risk_events
            (id, merchant_id, customer_id, customer_name, customer_phone, amount_in_cents, event_type, failure_code)
            VALUES ('evt_twilio_001', 'MER_001', 'CUST_TWILIO', 'Twilio Phone User', '+919999000002', 20000, 'PAYMENT_FAILED', 'CARD_EXPIRED')
            """
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO recovery_workflows
            (id, event_id, current_state, is_terminal)
            VALUES ('wf_twilio_001', 'evt_twilio_001', 'AWAITING_REPLY', 0)
            """
        )
        conn.commit()
        conn.close()

        # 2. Simulate Twilio payload: "Pay on Friday"
        resp1 = client.post("/api/webhook/twilio", data={
            "From": "whatsapp:+919999000002",
            "Body": "Pay on Friday"
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json()["status"], "PROMISE_RECORDED")
        self.assertEqual(resp1.json()["workflow"]["current_state"], "PROMISE_TO_PAY")
        print("Twilio webhook reply 'Pay on Friday' processed successfully -> state updated to PROMISE_TO_PAY.")

        # 3. Reset workflow for next check
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE recovery_workflows SET current_state = 'AWAITING_REPLY', is_terminal = 0 WHERE id = 'wf_twilio_001'")
        conn.commit()
        conn.close()

        # 4. Simulate Twilio payload: "band karo" (Opt-Out keyword)
        resp2 = client.post("/api/webhook/twilio", data={
            "From": "whatsapp:+919999000002",
            "Body": "band karo"
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["status"], "GUARD_BLOCKED")
        self.assertEqual(resp2.json()["workflow"]["current_state"], "DNC_LOCKED")
        print("Twilio webhook reply 'band karo' processed successfully -> blocked and state set to DNC_LOCKED.")


    def test_breach_auto_retriage(self):
        print("\n--- Running Breach Auto-ReTriage Tests ---")
        from fastapi.testclient import TestClient
        from backend.app.main import app

        client = TestClient(app)

        # 1. Create a promise to pay workflow to breach
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO at_risk_events
            (id, merchant_id, customer_id, customer_name, customer_email, customer_phone, amount_in_cents, event_type, failure_code)
            VALUES ('evt_breach_001', 'MER_001', 'CUST_BREACH', 'Breach User', 'breach@example.com', '+919999000003', 100000, 'PAYMENT_FAILED', 'UPI_DAILY_LIMIT_EXCEEDED')
            """
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO recovery_workflows
            (id, event_id, current_state, promise_breached, is_terminal)
            VALUES ('wf_breach_001', 'evt_breach_001', 'PROMISE_TO_PAY', 0, 0)
            """
        )
        conn.commit()
        conn.close()

        # 2. Trigger the simulated breach
        resp = client.post("/api/simulator/trigger-breach?workflow_id=wf_breach_001")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "BREACH_TRIGGERED")
        
        # Verify FSM moved past PROMISE_BREACHED due to re-triage (since UPI_DAILY_LIMIT recommends SILENT_RETRY -> RETRY_SCHEDULED)
        final_state = resp.json()["workflow"]["current_state"]
        self.assertEqual(final_state, "RETRY_SCHEDULED")
        
        # Confirm audit logs have the breach AND the auto re-triage records
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recovery_audit_logs WHERE workflow_id = 'wf_breach_001' ORDER BY id ASC")
        logs = [dict(r) for r in cursor.fetchall()]
        conn.close()

        self.assertGreaterEqual(len(logs), 2)
        self.assertEqual(logs[0]["to_state"], "PROMISE_BREACHED")
        self.assertEqual(logs[1]["to_state"], "RETRY_SCHEDULED")
        self.assertEqual(logs[1]["trigger_type"], "AUTO_RE_TRIAGE")
        print(f"Breach re-triage verified: FSM moved from PROMISE_TO_PAY -> PROMISE_BREACHED -> {final_state} automatically!")

if __name__ == "__main__":
    unittest.main()

