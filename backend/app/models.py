from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime

class AtRiskEventCreate(BaseModel):
    id: str
    merchant_id: str
    customer_id: str
    customer_name: str
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_tier: str = "STANDARD"
    amount_in_cents: int
    event_type: str
    failure_code: str
    natural_recovery_p: float = 0.12
    created_at: Optional[str] = None

class TriageResult(BaseModel):
    failure_diagnosis: str
    p_recovery: float
    expected_value_cents: int
    recommended_action: str
    scheduled_delay_minutes: int
    confidence_reasoning: str

class OutreachReplyRequest(BaseModel):
    workflow_id: str
    message_text: str

class SystemGuardResult(BaseModel):
    should_block: bool
    reason: str
    new_state: Optional[str] = None

class PaymentWebhookPayload(BaseModel):
    """
    Simulates a Razorpay payment.failed webhook payload.
    All fields except the three mandatory ones are optional — the system
    will handle missing email/phone by choosing the best available channel.
    """
    customer_name: str
    amount_in_cents: int
    failure_code: str
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_tier: str = "STANDARD"
    merchant_id: Optional[str] = "MER_001"
    razorpay_payment_id: Optional[str] = None  # e.g. pay_Nn4T3d8uW9kP2r
    event_type: str = "PAYMENT_FAILED"
