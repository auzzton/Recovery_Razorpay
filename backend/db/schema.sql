-- RecoveryOS PostgreSQL Compatible Schema

CREATE TABLE IF NOT EXISTS at_risk_events (
    id TEXT PRIMARY KEY,
    merchant_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(64) NOT NULL,
    customer_name VARCHAR(128),
    customer_phone VARCHAR(20),
    customer_email VARCHAR(128),
    customer_tier VARCHAR(32) DEFAULT 'STANDARD',
    amount_in_cents BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    failure_code VARCHAR(64),
    raw_payload TEXT,
    razorpay_payment_id VARCHAR(64),
    payment_captured BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recovery_workflows (
    id TEXT PRIMARY KEY,
    event_id TEXT REFERENCES at_risk_events(id),
    current_state VARCHAR(64) NOT NULL DEFAULT 'TRIAGED',
    p_recovery NUMERIC(3,2),
    expected_value_cents BIGINT,
    recommended_action VARCHAR(64),
    retry_count INT DEFAULT 0,
    contact_count INT DEFAULT 0,
    promise_to_pay_date TIMESTAMP,
    promise_breached BOOLEAN DEFAULT FALSE,
    is_terminal BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Partial Unique Index for preventing double-counting active workflows
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_workflow_per_event 
ON recovery_workflows (event_id) 
WHERE is_terminal = FALSE;

CREATE TABLE IF NOT EXISTS recovery_audit_logs (
    id SERIAL PRIMARY KEY,
    workflow_id TEXT REFERENCES recovery_workflows(id),
    from_state VARCHAR(64),
    to_state VARCHAR(64),
    trigger_type VARCHAR(64),
    actor VARCHAR(64),
    reasoning TEXT NOT NULL,
    payload TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
