import os
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict, Any

QUIET_START = 21 # 9 PM IST
QUIET_END = 9    # 9 AM IST
# TRAI compliance limits — configurable per deployment without code changes.
MAX_RETRIES          = int(os.environ.get("MAX_RETRIES",          "3"))
MAX_CONTACTS_PER_48H = int(os.environ.get("MAX_CONTACTS_PER_48H", "2"))
OPT_OUT_KEYWORDS = ["stop", "opt out", "unsubscribe", "band karo", "mat bhejo"]


def is_quiet_hours() -> bool:
    """Returns True if current time in IST is between 9 PM and 9 AM."""
    try:
        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        # Fallback if ZoneInfo fails on system without tz data
        now_ist = datetime.now(timezone.utc)
    h = now_ist.hour
    return h >= QUIET_START or h < QUIET_END

def run_system_guard(
    workflow: Dict[str, Any], 
    event: Dict[str, Any], 
    incoming_message: Optional[str] = None
) -> Tuple[bool | str, str, Optional[str]]:
    """
    Returns (should_block: bool | "DEFER", reason: str, new_state: str | None)
    The system guard ALWAYS runs before the LLM recommendation or action executes.
    """
    # Guard 1: Max retries
    retry_count = workflow.get("retry_count", 0)
    if retry_count >= MAX_RETRIES:
        return True, "MAX_RETRIES_EXCEEDED", "DNC_LOCKED"
    
    # Guard 2: Max contacts in 48h
    contact_count = workflow.get("contact_count", 0)
    if contact_count >= MAX_CONTACTS_PER_48H:
        return True, "MAX_CONTACTS_IN_48H_EXCEEDED", "DNC_LOCKED"
    
    # Guard 3: Customer opt-out
    if incoming_message:
        msg_lower = incoming_message.lower()
        if any(kw in msg_lower for kw in OPT_OUT_KEYWORDS):
            return True, "OPT_OUT_KEYWORD_DETECTED", "DNC_LOCKED"
    
    # Guard 4: Payment already captured (race condition prevention)
    if event.get("payment_captured"):
        return True, "PAYMENT_ALREADY_CAPTURED", "RECOVERED"
    
    # Guard 5: TRAI quiet hours (defer, not block permanently)
    if is_quiet_hours():
        return "DEFER", "TRAI_QUIET_HOURS", None
    
    return False, "ALL_GUARDS_PASSED", None
