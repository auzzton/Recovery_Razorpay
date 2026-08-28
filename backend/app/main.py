from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
import json
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.db.database import get_connection, dict_from_row, init_db
from backend.app.models import AtRiskEventCreate, OutreachReplyRequest, PaymentWebhookPayload
from backend.app.guards import run_system_guard, OPT_OUT_KEYWORDS
from backend.app.llm_provider import GeminiDecisionEngine, INTERVENTION_COSTS
from backend.app.fsm import transition_state, log_audit
from backend.app.synthetic_generator import seed_synthetic_dataset
from backend.app.date_parser import get_promise_date
from backend.app import razorpay_client
from backend.app.razorpay_client import RazorpayAPIError
from backend.app import outreach_dispatcher

logger = logging.getLogger(__name__)

app = FastAPI(title="RecoveryOS Backend API", version="1.0.0")

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

decision_engine = GeminiDecisionEngine()

# ---------------------------------------------------------------------------
# Background scheduler — auto-fires promise breach checks every 5 minutes
# ---------------------------------------------------------------------------
scheduler = BackgroundScheduler(timezone="UTC")


def check_and_trigger_breaches():
    """
    Background job: poll for PROMISE_TO_PAY workflows whose deadline
    (promise_to_pay_date + 2 hours) has passed WITHOUT a captured payment.
    Automatically transitions them to PROMISE_BREACHED.
    Runs every 5 minutes via APScheduler.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Find all active promise-to-pay workflows past their deadline
        cursor.execute(
            """
            SELECT id, promise_to_pay_date
            FROM recovery_workflows
            WHERE current_state = 'PROMISE_TO_PAY'
              AND promise_breached = 0
              AND promise_to_pay_date IS NOT NULL
              AND datetime(promise_to_pay_date, '+2 hours') <= datetime(?)
            """,
            (now_utc,)
        )
        overdue = cursor.fetchall()
        if overdue:
            logger.info(
                "[BreachChecker] Found %d overdue promise(s) at %s",
                len(overdue), now_utc
            )
        for row in overdue:
            wf_id = row["id"]
            try:
                transition_state(
                    workflow_id=wf_id,
                    to_state="PROMISE_BREACHED",
                    trigger_type="PROMISE_BREACH",
                    actor="SCHEDULER",
                    reasoning=(
                        f"Auto-breach: promise_to_pay_date + 2h elapsed "
                        f"with no payment captured (checked at {now_utc})."
                    ),
                    extra_updates={"promise_breached": True}
                )
                logger.info("[BreachChecker] Breached workflow %s", wf_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("[BreachChecker] Failed to breach %s: %s", wf_id, exc)
    finally:
        conn.close()


def process_scheduled_retries():
    """
    Background job: poll for RETRY_SCHEDULED workflows and fire a real
    Razorpay API capture call for each one.

    Flow per workflow:
      1. Fetch razorpay_payment_id + amount from DB.
      2. Call Razorpay GET /v1/payments/{id} then POST /v1/payments/{id}/capture.
      3a. On success  → transition to RECOVERED, mark payment_captured=1.
      3b. On API error → increment retry_count.
             - If retry_count >= MAX_RETRIES → transition to DNC_LOCKED.
             - Otherwise    → leave in RETRY_SCHEDULED for next poll.
    """
    MAX_RETRIES = 3
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT w.id as workflow_id, w.retry_count,
                   e.razorpay_payment_id, e.amount_in_cents, e.id as event_id
            FROM recovery_workflows w
            JOIN at_risk_events e ON w.event_id = e.id
            WHERE w.current_state = 'RETRY_SCHEDULED'
              AND w.is_terminal = 0
            """
        )
        pending = cursor.fetchall()
        if pending:
            logger.info(
                "[RetryScheduler] Processing %d RETRY_SCHEDULED workflow(s).",
                len(pending)
            )
    finally:
        conn.close()

    for row in pending:
        wf_id          = row["workflow_id"]
        retry_count    = row["retry_count"] or 0
        payment_id     = row["razorpay_payment_id"]
        amount_cents   = row["amount_in_cents"]
        event_id       = row["event_id"]

        if not payment_id:
            logger.warning(
                "[RetryScheduler] Workflow %s has no razorpay_payment_id — skipping.", wf_id
            )
            continue

        logger.info(
            "[RetryScheduler] Attempting Razorpay capture for workflow=%s payment=%s amount=%d",
            wf_id, payment_id, amount_cents
        )

        try:
            rzp_result = razorpay_client.retry_payment_with_fallback(
                payment_id=payment_id,
                amount_in_cents=amount_cents,
            )
            # ── SUCCESS PATH ──────────────────────────────────────────────
            # Mark payment_captured on the event row
            conn2 = get_connection()
            try:
                conn2.cursor().execute(
                    "UPDATE at_risk_events SET payment_captured = 1 WHERE id = ?",
                    (event_id,)
                )
                conn2.commit()
            finally:
                conn2.close()

            transition_state(
                workflow_id=wf_id,
                to_state="RECOVERED",
                trigger_type="SILENT_RETRY",
                actor="RAZORPAY_API",
                reasoning=(
                    f"Razorpay capture succeeded for payment {payment_id}. "
                    f"HTTP 200. Status: {rzp_result.get('razorpay_status', 'captured')}."
                ),
                payload={
                    "razorpay_payment_id": payment_id,
                    "razorpay_status":     rzp_result.get("razorpay_status"),
                    "http_status":         rzp_result.get("http_status"),
                },
            )
            logger.info(
                "[RetryScheduler] Workflow %s RECOVERED via Razorpay payment %s.",
                wf_id, payment_id
            )

        except RazorpayAPIError as exc:
            # ── FAILURE PATH ──────────────────────────────────────────────
            new_retry_count = retry_count + 1
            logger.warning(
                "[RetryScheduler] Razorpay capture FAILED for workflow=%s payment=%s "
                "HTTP=%d retries=%d/%d. Error: %s",
                wf_id, payment_id, exc.status_code,
                new_retry_count, MAX_RETRIES, exc.error_body
            )

            if new_retry_count >= MAX_RETRIES:
                transition_state(
                    workflow_id=wf_id,
                    to_state="DNC_LOCKED",
                    trigger_type="SILENT_RETRY",
                    actor="RAZORPAY_API",
                    reasoning=(
                        f"Razorpay capture failed {new_retry_count}/{MAX_RETRIES} times "
                        f"for payment {payment_id}. HTTP {exc.status_code}. "
                        f"Escalating to DNC_LOCKED."
                    ),
                    payload={
                        "razorpay_payment_id": payment_id,
                        "http_status":         exc.status_code,
                        "error":               exc.error_body,
                    },
                    extra_updates={"retry_count": new_retry_count},
                )
            else:
                # Increment retry_count in place — remain RETRY_SCHEDULED
                conn3 = get_connection()
                try:
                    conn3.cursor().execute(
                        "UPDATE recovery_workflows SET retry_count = ? WHERE id = ?",
                        (new_retry_count, wf_id)
                    )
                    conn3.commit()
                finally:
                    conn3.close()

                logger.info(
                    "[RetryScheduler] Workflow %s retry_count now %d — will retry next cycle.",
                    wf_id, new_retry_count
                )

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[RetryScheduler] Unexpected error for workflow %s: %s", wf_id, exc
            )



@app.on_event("startup")
def startup_event():
    init_db()
    # Auto-seed database if empty
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM at_risk_events")
    row = cursor.fetchone()
    if row and row["cnt"] == 0:
        seed_synthetic_dataset(100)
    conn.close()

    # Start background breach-checker — polls every 5 minutes
    scheduler.add_job(
        check_and_trigger_breaches,
        trigger=IntervalTrigger(minutes=5),
        id="promise_breach_checker",
        name="Promise Breach Auto-Checker",
        replace_existing=True,
    )
    # Start Razorpay silent-retry executor — polls every 5 minutes
    scheduler.add_job(
        process_scheduled_retries,
        trigger=IntervalTrigger(minutes=5),
        id="razorpay_retry_executor",
        name="Razorpay Silent Retry Executor",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[Scheduler] Started — breach checker + Razorpay retry executor, both polling every 5 min."
    )


@app.on_event("shutdown")
def shutdown_event():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Scheduler shut down.")

@app.post("/api/seed")
def seed_data(num_records: int = 100):
    cnt = seed_synthetic_dataset(num_records)
    return {"message": f"Successfully seeded {cnt} records"}

@app.get("/api/merchants")
def list_merchants():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT merchant_id FROM at_risk_events ORDER BY merchant_id")
    rows = cursor.fetchall()
    conn.close()
    return [r["merchant_id"] for r in rows]

@app.get("/api/dashboard/summary")
def get_dashboard_summary(merchant_id: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    
    where_clause = ""
    params = []
    if merchant_id and merchant_id != "ALL":
        where_clause = "WHERE e.merchant_id = ?"
        params.append(merchant_id)
        
    query = f"""
        SELECT 
            e.id as event_id,
            e.merchant_id,
            e.amount_in_cents,
            w.id as workflow_id,
            w.current_state,
            w.recommended_action,
            w.p_recovery
        FROM at_risk_events e
        JOIN recovery_workflows w ON e.id = w.event_id
        {where_clause}
    """
    cursor.execute(query, params)
    rows = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    
    total_events = len(rows)
    total_at_risk_cents = sum(r["amount_in_cents"] for r in rows)
    
    # Counterfactual Benchmark: Natural Recovery Rate = 12% (RBI NACH return rate benchmark)
    natural_recovery_p = 0.12
    natural_recovery_cents = int(total_at_risk_cents * natural_recovery_p)
    
    # RecoveryOS Recovered (RECOVERED state)
    recovered_rows = [r for r in rows if r["current_state"] == "RECOVERED"]
    recovered_cents = sum(r["amount_in_cents"] for r in recovered_rows)
    recovery_rate_pct = (recovered_cents / total_at_risk_cents * 100) if total_at_risk_cents > 0 else 0
    
    # AI Delta (Incremental Recovery above natural baseline)
    incremental_recovery_cents = max(0, recovered_cents - natural_recovery_cents)
    incremental_rate_pct = (incremental_recovery_cents / total_at_risk_cents * 100) if total_at_risk_cents > 0 else 0
    
    # Cost of All Interventions
    total_intervention_cost_cents = 0
    for r in rows:
        action = r.get("recommended_action", "SILENT_RETRY")
        cost = INTERVENTION_COSTS.get(action, 0)
        total_intervention_cost_cents += cost

    # Net Revenue Gain = Incremental Recovery - Intervention Cost
    net_gain_cents = incremental_recovery_cents - total_intervention_cost_cents
    
    # ROI = (Net Gain / Cost) * 100
    roi_pct = (net_gain_cents / total_intervention_cost_cents * 100) if total_intervention_cost_cents > 0 else 0

    # State Distribution
    state_counts = {}
    for r in rows:
        st = r["current_state"]
        state_counts[st] = state_counts.get(st, 0) + 1
        
    # Action Breakdown
    action_counts = {}
    for r in rows:
        act = r.get("recommended_action") or "SILENT_RETRY"
        action_counts[act] = action_counts.get(act, 0) + 1

    return {
        "total_events": total_events,
        "revenue_at_risk_rupees": total_at_risk_cents / 100,
        "natural_recovery_rupees": natural_recovery_cents / 100,
        "natural_recovery_pct": natural_recovery_p * 100,
        "recovery_os_recovered_rupees": recovered_cents / 100,
        "recovery_os_rate_pct": round(recovery_rate_pct, 1),
        "incremental_ai_delta_rupees": incremental_recovery_cents / 100,
        "incremental_rate_pct": round(incremental_rate_pct, 1),
        "total_intervention_cost_rupees": total_intervention_cost_cents / 100,
        "net_revenue_gain_rupees": net_gain_cents / 100,
        "roi_pct": round(roi_pct, 1),
        "state_distribution": state_counts,
        "action_breakdown": action_counts
    }

@app.get("/api/dashboard/workflows")
def list_workflows(
    merchant_id: Optional[str] = None,
    state: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    conn = get_connection()
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    if merchant_id and merchant_id != "ALL":
        conditions.append("e.merchant_id = ?")
        params.append(merchant_id)
        
    if state and state != "ALL":
        conditions.append("w.current_state = ?")
        params.append(state)
        
    if search:
        conditions.append("(e.customer_name LIKE ? OR e.customer_phone LIKE ? OR e.failure_code LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
        
    where_str = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    query = f"""
        SELECT 
            w.id as workflow_id,
            w.event_id,
            w.current_state,
            w.p_recovery,
            w.expected_value_cents,
            w.recommended_action,
            w.retry_count,
            w.contact_count,
            w.promise_to_pay_date,
            w.promise_breached,
            w.is_terminal,
            w.updated_at,
            e.merchant_id,
            e.customer_id,
            e.customer_name,
            e.customer_phone,
            e.customer_tier,
            e.amount_in_cents,
            e.event_type,
            e.failure_code,
            e.created_at as event_created_at
        FROM recovery_workflows w
        JOIN at_risk_events e ON w.event_id = e.id
        {where_str}
        ORDER BY w.updated_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/workflows/{workflow_id}/audit")
def get_workflow_audit_log(workflow_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT 
            w.*, 
            e.customer_name, e.customer_phone, e.amount_in_cents, e.failure_code, e.merchant_id, e.customer_tier
        FROM recovery_workflows w
        JOIN at_risk_events e ON w.event_id = e.id
        WHERE w.id = ?
        """,
        (workflow_id,)
    )
    wf = dict_from_row(cursor.fetchone())
    if not wf:
        conn.close()
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    cursor.execute(
        "SELECT * FROM recovery_audit_logs WHERE workflow_id = ? ORDER BY id ASC",
        (workflow_id,)
    )
    audit_logs = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    
    return {
        "workflow": wf,
        "audit_logs": audit_logs
    }

@app.post("/api/simulator/reply")
def simulate_customer_reply(req: OutreachReplyRequest):
    """
    Simulator endpoint: Send incoming customer reply.
    Checks System Guard first for opt-out intent ("band karo", "stop").
    Parses promise-to-pay ("Pay on Friday").
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT w.*, e.customer_name, e.failure_code, e.amount_in_cents, e.payment_captured "
        "FROM recovery_workflows w JOIN at_risk_events e ON w.event_id = e.id WHERE w.id = ?",
        (req.workflow_id,)
    )
    row = dict_from_row(cursor.fetchone())
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")

    event_dict = {
        "id": row["event_id"],
        "payment_captured": row.get("payment_captured", False)
    }

    # Step 1: Execute System Guard ALWAYS first
    should_block, reason, guard_state = run_system_guard(row, event_dict, incoming_message=req.message_text)
    
    if should_block and guard_state:
        updated_wf = transition_state(
            workflow_id=req.workflow_id,
            to_state=guard_state,
            trigger_type="OPT_OUT" if reason == "OPT_OUT_KEYWORD_DETECTED" else "RULE_VIOLATION",
            actor="SYSTEM_GUARD",
            reasoning=f"System Guard halted workflow: {reason} (Incoming: '{req.message_text}')",
            payload={"incoming_message": req.message_text, "guard_reason": reason}
        )
        return {
            "status": "GUARD_BLOCKED",
            "message": f"System Guard triggered: {reason}",
            "workflow": updated_wf
        }

    # Step 2: Parse message for Promise-To-Pay vs Payment Confirmation
    text = req.message_text.lower()
    if "paid" in text or "done" in text:
        updated_wf = transition_state(
            workflow_id=req.workflow_id,
            to_state="RECOVERED",
            trigger_type="USER_INPUT",
            actor="AGENT_BRAIN",
            reasoning="Customer confirmed payment completion.",
            payload={"incoming_message": req.message_text}
        )
        return {"status": "SUCCESS", "message": "Payment confirmed. Workflow set to RECOVERED.", "workflow": updated_wf}
    
    # Parse promise date using NLP — "Pay on Friday", "tomorrow", "next week", etc.
    promise_date = get_promise_date(req.message_text)
    promise_date_display = promise_date[:10]  # YYYY-MM-DD for human-readable message

    logger.info(
        "[ReplySimulator] Parsed promise date from '%s' → %s",
        req.message_text, promise_date
    )

    updated_wf = transition_state(
        workflow_id=req.workflow_id,
        to_state="PROMISE_TO_PAY",
        trigger_type="USER_INPUT",
        actor="AGENT_BRAIN",
        reasoning=(
            f"Customer promised payment: '{req.message_text}'. "
            f"NLP extracted promise date: {promise_date}. "
            f"Breach check auto-scheduled via background scheduler (promise_date + 2h)."
        ),
        payload={"incoming_message": req.message_text, "promise_to_pay_date": promise_date},
        extra_updates={"promise_to_pay_date": promise_date, "promise_breached": False}
    )

    return {
        "status": "PROMISE_RECORDED",
        "message": f"Promise to pay recorded for {promise_date_display}. Auto-breach check active (every 5 min).",
        "workflow": updated_wf,
        "parsed_promise_date": promise_date
    }

@app.post("/api/simulator/trigger-breach")
def trigger_promise_breach(workflow_id: str):
    """Simulates automated background job detecting promise date passed without payment."""
    updated_wf = transition_state(
        workflow_id=workflow_id,
        to_state="PROMISE_BREACHED",
        trigger_type="PROMISE_BREACH",
        actor="SCHEDULER",
        reasoning="Scheduled breach check detected promise_to_pay_date passed + 2h with no payment captured.",
        extra_updates={"promise_breached": True}
    )
    return {"status": "BREACH_TRIGGERED", "workflow": updated_wf}


@app.post("/api/webhook/razorpay")
def ingest_payment_webhook(payload: PaymentWebhookPayload):
    """
    Simulates a Razorpay payment.failed webhook.

    Full automated pipeline on every call:
      1. Persist the at-risk event record.
      2. Run System Guard (rate limits, DNC checks).
      3. Run AI Triage (Gemini or heuristic fallback) to score the event.
      4. Create the recovery workflow in the appropriate FSM state.
      5. If triage recommends outreach (any action != SILENT_RETRY / DO_NOT_CONTACT),
         automatically dispatch a live email (primary) or WhatsApp (fallback)
         without any manual intervention.
      6. Log the exact outreach channel in the immutable audit ledger.
    """
    import uuid, string, random
    now_utc = datetime.now(timezone.utc)

    # --- Build IDs -----------------------------------------------------------
    event_id    = str(uuid.uuid4())
    customer_id = f"CUST_{uuid.uuid4().hex[:6].upper()}"
    workflow_id = str(uuid.uuid4())
    rzp_pay_id  = (
        payload.razorpay_payment_id
        or "pay_" + "".join(random.choices(string.ascii_letters + string.digits, k=16))
    )

    # --- Persist event -------------------------------------------------------
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO at_risk_events
            (id, merchant_id, customer_id, customer_name, customer_phone,
             customer_email, customer_tier, amount_in_cents, event_type,
             failure_code, razorpay_payment_id, payment_captured, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                event_id, payload.merchant_id, customer_id, payload.customer_name,
                payload.customer_phone, payload.customer_email, payload.customer_tier,
                payload.amount_in_cents, payload.event_type, payload.failure_code,
                rzp_pay_id, now_utc.isoformat()
            )
        )
        # Create initial TRIAGED workflow row
        cursor.execute(
            """
            INSERT INTO recovery_workflows
            (id, event_id, current_state, retry_count, contact_count,
             promise_breached, is_terminal, updated_at)
            VALUES (?, ?, 'TRIAGED', 0, 0, 0, 0, ?)
            """,
            (workflow_id, event_id, now_utc.isoformat())
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "[Webhook] Ingested payment failure event=%s workflow=%s customer=%s failure=%s",
        event_id, workflow_id, payload.customer_name, payload.failure_code
    )

    # --- System Guard --------------------------------------------------------
    event_dict    = {"id": event_id, "payment_captured": False}
    workflow_dict = {"id": workflow_id, "retry_count": 0, "contact_count": 0}
    should_block, guard_reason, guard_state = run_system_guard(workflow_dict, event_dict)

    if should_block and guard_state:
        updated_wf = transition_state(
            workflow_id=workflow_id,
            to_state=guard_state,
            trigger_type="RULE_VIOLATION",
            actor="SYSTEM_GUARD",
            reasoning=f"System Guard halted: {guard_reason}",
        )
        return {
            "status": "GUARD_BLOCKED",
            "event_id": event_id,
            "workflow_id": workflow_id,
            "guard_reason": guard_reason,
            "workflow": updated_wf,
        }

    # --- AI Triage -----------------------------------------------------------
    event_full = {
        "id":                event_id,
        "customer_name":     payload.customer_name,
        "customer_tier":     payload.customer_tier,
        "amount_in_cents":   payload.amount_in_cents,
        "failure_code":      payload.failure_code,
        "razorpay_payment_id": rzp_pay_id,
    }
    triage = decision_engine.triage_event(event_full, workflow_dict)

    # Map recommended action to target FSM state
    _ACTION_STATE_MAP = {
        "SILENT_RETRY":       "RETRY_SCHEDULED",
        "WHATSAPP_REMINDER":  "AWAITING_REPLY",
        "VOICE_INTERVENTION": "AWAITING_REPLY",
        "HUMAN_ESCALATION":   "ESCALATED",
        "DO_NOT_CONTACT":     "DNC_LOCKED",
    }
    target_state = _ACTION_STATE_MAP.get(triage.recommended_action, "TRIAGED")
    is_terminal  = target_state in {"DNC_LOCKED", "PERMANENTLY_FAILED"}

    # --- Dispatch Outreach ---------------------------------------------------
    outreach_result = None
    OUTREACH_ACTIONS = {"WHATSAPP_REMINDER", "VOICE_INTERVENTION", "HUMAN_ESCALATION"}

    if triage.recommended_action in OUTREACH_ACTIONS:
        payment_url  = f"https://rzp.io/l/rec_{event_id[:8]}"
        message_body = decision_engine.generate_outreach_message(event_full)

        outreach_result = outreach_dispatcher.send_payment_reminder(
            customer_name   = payload.customer_name,
            customer_email  = payload.customer_email,
            customer_phone  = payload.customer_phone,
            amount_in_cents = payload.amount_in_cents,
            failure_code    = payload.failure_code,
            payment_url     = payment_url,
            message_body    = message_body,
            event_id        = event_id,
        )
        logger.info(
            "[Webhook] Outreach dispatched for workflow=%s via channel=%s status=%s",
            workflow_id, outreach_result.get("channel"), outreach_result.get("status")
        )

    # --- FSM Transition + Audit Log ------------------------------------------
    triage_reasoning = (
        f"AI Triage: {triage.confidence_reasoning}. "
        f"P(recovery)={triage.p_recovery}. "
        f"E[Value]=₹{triage.expected_value_cents/100:.2f}."
    )
    if outreach_result:
        channel   = outreach_result.get("channel", "UNKNOWN")
        prov_id   = outreach_result.get("provider_id") or ""
        triage_reasoning += (
            f" Outreach dispatched via {channel}"
            + (f" (id: {prov_id})" if prov_id else "")
            + "."
        )

    updated_wf = transition_state(
        workflow_id = workflow_id,
        to_state    = target_state,
        trigger_type= "WEBHOOK_INGEST",
        actor       = "AGENT_BRAIN",
        reasoning   = triage_reasoning,
        payload     = {
            "recommended_action":  triage.recommended_action,
            "failure_diagnosis":   triage.failure_diagnosis,
            "outreach":            outreach_result,
            "razorpay_payment_id": rzp_pay_id,
        },
        extra_updates={
            "p_recovery":          triage.p_recovery,
            "expected_value_cents":triage.expected_value_cents,
            "recommended_action":  triage.recommended_action,
            "contact_count":       1 if outreach_result else 0,
            "is_terminal":         is_terminal,
        }
    )

    return {
        "status":           "PROCESSED",
        "event_id":         event_id,
        "workflow_id":      workflow_id,
        "razorpay_payment_id": rzp_pay_id,
        "triage": {
            "recommended_action": triage.recommended_action,
            "p_recovery":         triage.p_recovery,
            "fsm_state":          target_state,
        },
        "outreach":         outreach_result,
        "workflow":         updated_wf,
    }
