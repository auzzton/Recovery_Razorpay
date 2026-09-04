import os
import sys

# Ensure project root is in sys.path when module is loaded directly
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from backend.db.database import get_connection, dict_from_row, PLACEHOLDER

TERMINAL_STATES = {"RECOVERED", "DNC_LOCKED", "PERMANENTLY_FAILED"}

def log_audit(
    conn,
    workflow_id: str,
    from_state: str,
    to_state: str,
    trigger_type: str,
    actor: str,
    reasoning: str,
    payload: Optional[Dict[str, Any]] = None
):
    """Immutable audit ledger log writer. Never updates or deletes existing rows."""
    cursor = conn.cursor()
    payload_json = json.dumps(payload) if payload else None
    cursor.execute(
        f"""
        INSERT INTO recovery_audit_logs 
        (workflow_id, from_state, to_state, trigger_type, actor, reasoning, payload, created_at)
        VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER})
        """,
        (
            workflow_id,
            from_state,
            to_state,
            trigger_type,
            actor,
            reasoning,
            payload_json,
            datetime.now(timezone.utc).isoformat()
        )
    )

def transition_state(
    workflow_id: str,
    to_state: str,
    trigger_type: str,
    actor: str,
    reasoning: str,
    payload: Optional[Dict[str, Any]] = None,
    extra_updates: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Execute state machine transition with audit logging."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(f"SELECT * FROM recovery_workflows WHERE id = {PLACEHOLDER}", (workflow_id,))
    wf = dict_from_row(cursor.fetchone())
    if not wf:
        conn.close()
        raise ValueError(f"Workflow {workflow_id} not found")
    
    from_state = wf["current_state"]
    is_terminal = to_state in TERMINAL_STATES
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Build update query using the correct placeholder for the active DB backend
    update_fields = [f"current_state = {PLACEHOLDER}", f"is_terminal = {PLACEHOLDER}", f"updated_at = {PLACEHOLDER}"]
    params = [to_state, is_terminal, now_iso]
    
    if extra_updates:
        for key, val in extra_updates.items():
            update_fields.append(f"{key} = {PLACEHOLDER}")
            params.append(val)
            
    params.append(workflow_id)
    
    cursor.execute(
        f"UPDATE recovery_workflows SET {', '.join(update_fields)} WHERE id = {PLACEHOLDER}",
        params
    )
    
    log_audit(conn, workflow_id, from_state, to_state, trigger_type, actor, reasoning, payload)
    
    conn.commit()
    
    cursor.execute(f"SELECT * FROM recovery_workflows WHERE id = {PLACEHOLDER}", (workflow_id,))
    updated_wf = dict_from_row(cursor.fetchone())
    conn.close()
    return updated_wf
