import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from backend.app.models import TriageResult

logger = logging.getLogger(__name__)

# Lazily import google.generativeai to avoid app launch failure if SDK is not installed yet
try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# Intervention costs in paise (1 INR = 100 paise).
# Configurable via env vars so operators can reflect real Twilio/Resend pricing without touching code.
INTERVENTION_COSTS = {
    "SILENT_RETRY":       0,
    "WHATSAPP_REMINDER":  int(os.environ.get("WHATSAPP_COST_PAISE", "500")),    # default ₹5
    "VOICE_INTERVENTION": int(os.environ.get("VOICE_COST_PAISE",    "2500")),   # default ₹25
    "HUMAN_ESCALATION":   int(os.environ.get("HUMAN_COST_PAISE",    "25000")),  # default ₹250
    "DO_NOT_CONTACT":     0,
}

# Hand-tuned recovery probability priors.
# IMPORTANT: These are NOT derived from real Razorpay transaction data.
# They are heuristic estimates for demo/development, informed by domain knowledge
# and RBI NACH return patterns. Replace with merchant-specific historical rates in production.
FAILURE_CODE_BASE_PROBABILITY = {
    "INSUFFICIENT_FUNDS": 0.72,
    "CARD_EXPIRED": 0.55,
    "BANK_DOWNTIME": 0.88,
    "UPI_DAILY_LIMIT_EXCEEDED": 0.65,
    "MANDATE_BOUNCE_INSUFFICIENT_BALANCE": 0.70,
    "NETWORK_TIMEOUT": 0.82,
    "USER_DROPPED_PAYMENT_PAGE": 0.40,
    "CARD_BLOCKED": 0.30
}

class BaseLLMProvider(ABC):
    """Abstract interface for LLM Decision Engine. Swap models seamlessly."""
    
    @abstractmethod
    def triage_event(self, event: Dict[str, Any], workflow_context: Dict[str, Any]) -> TriageResult:
        pass

    @abstractmethod
    def generate_outreach_message(self, event: Dict[str, Any]) -> str:
        pass


class HeuristicDecisionEngine(BaseLLMProvider):
    """
    Fallback / Decoupled Decision Engine implementing the exact blueprint triage rules
    and Expected Value calculations without external LLM API dependency.
    """

    def triage_event(self, event: Dict[str, Any], workflow_context: Dict[str, Any]) -> TriageResult:
        failure_code = event.get("failure_code") or "UNKNOWN"
        amount = event.get("amount_in_cents", 0)
        tier = event.get("customer_tier", "STANDARD")
        retry_count = workflow_context.get("retry_count", 0)

        # Rule: Max retries exceeded -> DO_NOT_CONTACT
        if retry_count >= 3:
            return TriageResult(
                failure_diagnosis="Max retries reached. Halted to prevent spam.",
                p_recovery=0.0,
                expected_value_cents=0,
                recommended_action="DO_NOT_CONTACT",
                scheduled_delay_minutes=0,
                confidence_reasoning="Retry limit reached (>=3)."
            )

        # Base Probability
        p_recovery = FAILURE_CODE_BASE_PROBABILITY.get(failure_code, 0.50)
        
        # Rule: BANK_DOWNTIME -> SILENT_RETRY first
        if failure_code == "BANK_DOWNTIME":
            action = "SILENT_RETRY"
            reasoning = "Bank servers reported temporary downtime. Silent retry scheduled after bank sync window."
            delay = 360 # 6 hours
        elif failure_code in ["NETWORK_TIMEOUT", "UPI_DAILY_LIMIT_EXCEEDED"]:
            action = "SILENT_RETRY"
            reasoning = "Transient network issue or daily limit reset expected tomorrow."
            delay = 720 # 12 hours
        else:
            # Evaluate actions based on E[Value] = P(recovery) * amount - cost
            candidate_actions = ["SILENT_RETRY", "WHATSAPP_REMINDER", "VOICE_INTERVENTION", "HUMAN_ESCALATION"]
            
            best_action = "SILENT_RETRY"
            best_ev = -100000000

            for candidate in candidate_actions:
                # Rule: amount < 500 INR (50000 cents) -> never recommend HUMAN_ESCALATION
                if candidate == "HUMAN_ESCALATION" and amount < 50000:
                    continue
                # Rule: VIP prefer WHATSAPP over VOICE
                if candidate == "VOICE_INTERVENTION" and tier == "VIP":
                    continue

                cost = INTERVENTION_COSTS[candidate]
                ev = int((p_recovery * amount) - cost)

                if ev > best_ev:
                    best_ev = ev
                    best_action = candidate

            action = best_action
            reasoning = f"Selected {action} based on max E[Value] (₹{best_ev/100:.2f}) given failure code {failure_code} and tier {tier}."
            delay = 60 if action == "WHATSAPP_REMINDER" else 180

        cost = INTERVENTION_COSTS.get(action, 0)
        ev_cents = int((p_recovery * amount) - cost)

        return TriageResult(
            failure_diagnosis=f"Root cause: {failure_code.lower().replace('_', ' ')}",
            p_recovery=round(p_recovery, 2),
            expected_value_cents=ev_cents,
            recommended_action=action,
            scheduled_delay_minutes=delay,
            confidence_reasoning=reasoning
        )

    def generate_outreach_message(self, event: Dict[str, Any]) -> str:
        name = event.get("customer_name", "Customer")
        amount_rupees = f"₹{event.get('amount_in_cents', 0) / 100:,.2f}"
        failure = event.get("failure_code", "payment failure")
        
        return (
            f"Hi {name}, your payment of {amount_rupees} could not be processed due to {failure.lower().replace('_', ' ')}. "
            f"Please complete your payment here: https://rzp.io/l/rec_{event.get('id', '')[:8]}\n"
            f"Reply STOP to opt out."
        )


class GeminiDecisionEngine(BaseLLMProvider):
    """
    Intelligent AI Decision Engine powered by Google Gemini.
    Enforces strict rules via prompts while leveraging LLM diagnostic logic.
    Gracefully falls back to HeuristicDecisionEngine if API keys are missing or calls fail.
    """

    def __init__(self):
        self.heuristic_fallback = HeuristicDecisionEngine()
        self.model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.api_key = os.environ.get("GEMINI_API_KEY")

        if _GENAI_AVAILABLE and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.client_ready = True
                logger.info("[Gemini] Engine initialized using model: %s", self.model_name)
            except Exception as e:
                logger.warning("[Gemini] SDK configuration failed: %s. Using heuristic fallback.", e)
                self.client_ready = False
        else:
            self.client_ready = False
            logger.info("[Gemini] API key or SDK missing. Using heuristic fallback engine.")

    def triage_event(self, event: Dict[str, Any], workflow_context: Dict[str, Any]) -> TriageResult:
        if not self.client_ready:
            return self.heuristic_fallback.triage_event(event, workflow_context)

        # Basic constraints check (always bypass LLM for absolute state limits to keep execution safe)
        retry_count = workflow_context.get("retry_count", 0)
        contact_count = workflow_context.get("contact_count", 0)
        if retry_count >= 3 or contact_count >= 2:
            return self.heuristic_fallback.triage_event(event, workflow_context)

        prompt = f"""
Analyze this failed payment event for triage and recovery actions:
- Customer Name: {event.get('customer_name')}
- Customer Tier: {event.get('customer_tier', 'STANDARD')}
- Amount: ₹{event.get('amount_in_cents', 0) / 100:.2f} ({event.get('amount_in_cents')} cents)
- Failure Code: {event.get('failure_code')}
- Current Retry Count: {retry_count}
- Contact Count: {contact_count}

Available Actions:
- SILENT_RETRY (Cost: ₹0): Auto-retry. Good for temporary bank downtimes (BANK_DOWNTIME) or network timeout.
- WHATSAPP_REMINDER (Cost: ₹5): WhatsApp nudge. Good for CARD_EXPIRED, INSUFFICIENT_FUNDS.
- VOICE_INTERVENTION (Cost: ₹25): Automated call. Good for mid-to-high value standard accounts. DO NOT use for VIP tier.
- HUMAN_ESCALATION (Cost: ₹250): Account manager outreach. ONLY for high value transactions >= ₹500 (50000 cents).
- DO_NOT_CONTACT (Cost: ₹0): Permanently failed or opted out.

Formulate the TriageResult with these rules:
1. Recommend the best action that maximizes Expected Value: E[Value] = P(recovery) * amount - cost.
2. If amount is less than 50000 cents (₹500), you must NEVER choose HUMAN_ESCALATION.
3. If Customer Tier is 'VIP', you must NEVER choose VOICE_INTERVENTION (VIPs prefer WhatsApp).
4. Provide a detailed diagnosis of the failure code.
5. Provide a realistic recovery probability (p_recovery) between 0.0 and 1.0.
"""
        try:
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction="You are an AI Revenue Recovery specialist that triages transaction failures."
            )
            config = genai.types.GenerationConfig(
                response_mime_type="application/json",
                response_schema=TriageResult,
                temperature=0.1
            )
            response = model.generate_content(prompt, generation_config=config)
            data = json.loads(response.text)
            
            # Map values back to schema object
            return TriageResult(
                failure_diagnosis=data.get("failure_diagnosis"),
                p_recovery=round(float(data.get("p_recovery", 0.5)), 2),
                expected_value_cents=int(data.get("expected_value_cents", 0)),
                recommended_action=data.get("recommended_action", "SILENT_RETRY"),
                scheduled_delay_minutes=int(data.get("scheduled_delay_minutes", 60)),
                confidence_reasoning=data.get("confidence_reasoning")
            )
        except Exception as exc:
            logger.warning("[Gemini] API error during triage: %s. Falling back to heuristics.", exc)
            return self.heuristic_fallback.triage_event(event, workflow_context)

    def generate_outreach_message(self, event: Dict[str, Any]) -> str:
        if not self.client_ready:
            return self.heuristic_fallback.generate_outreach_message(event)

        prompt = f"""
Draft a personalized, high-converting WhatsApp payment recovery outreach message.
- Customer Name: {event.get('customer_name')}
- Amount: ₹{event.get('amount_in_cents', 0) / 100:.2f}
- Failure Cause: {event.get('failure_code', 'payment failure').replace('_', ' ').lower()}
- Payment URL: https://rzp.io/l/rec_{event.get('id', '')[:8]}

Guidelines:
- Keep it highly professional, polite, and direct.
- Explain the reason for failure constructively.
- Ensure it includes the payment link.
- Must end with: "Reply STOP to opt out."
- Keep it under 3 sentences. Do not use extra formatting or markdown.
"""
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as exc:
            logger.warning("[Gemini] API error during outreach generation: %s. Falling back.", exc)
            return self.heuristic_fallback.generate_outreach_message(event)
