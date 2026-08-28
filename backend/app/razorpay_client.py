"""
Razorpay API Client
~~~~~~~~~~~~~~~~~~~
Wraps the two endpoints needed for payment recovery:
  - GET  /v1/payments/{payment_id}        — fetch payment status
  - POST /v1/payments/{payment_id}/capture — capture an authorised payment

Keys are read from environment variables:
  RAZORPAY_KEY_ID     (default: rzp_test_DEMO_KEY — Razorpay test mode prefix)
  RAZORPAY_KEY_SECRET (default: DEMO_SECRET)

In a real deployment, inject real test-mode keys via .env / secrets manager.
The client will ALWAYS attempt the real HTTP call and return the response.
Callers decide whether to treat a 4xx/5xx as a simulated success for demo mode.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"
DEFAULT_TIMEOUT_S = 10  # seconds

# ---------------------------------------------------------------------------
# Credentials — override via environment variables in production/CI
# ---------------------------------------------------------------------------
_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_RecoveryOS_DEMO")
_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "RecoveryOS_DEMO_SECRET")


class RazorpayAPIError(Exception):
    """Raised when the Razorpay API returns a non-2xx response."""
    def __init__(self, status_code: int, error_body: Dict[str, Any]):
        self.status_code = status_code
        self.error_body = error_body
        super().__init__(f"Razorpay API error {status_code}: {error_body}")


def _auth() -> tuple[str, str]:
    return (_KEY_ID, _KEY_SECRET)


def fetch_payment(payment_id: str) -> Dict[str, Any]:
    """
    GET /v1/payments/{payment_id}
    Returns the payment object dict from Razorpay.
    Raises RazorpayAPIError on non-2xx.

    Example response fields:
        id, entity, amount, currency, status, captured,
        description, order_id, error_code, error_description, ...
    """
    url = f"{RAZORPAY_BASE_URL}/payments/{payment_id}"
    logger.info("[Razorpay] GET %s", url)

    resp = requests.get(url, auth=_auth(), timeout=DEFAULT_TIMEOUT_S)

    logger.info(
        "[Razorpay] fetch_payment(%s) → HTTP %d", payment_id, resp.status_code
    )

    if resp.ok:
        return resp.json()

    raise RazorpayAPIError(resp.status_code, resp.json())


def capture_payment(payment_id: str, amount_in_cents: int, currency: str = "INR") -> Dict[str, Any]:
    """
    POST /v1/payments/{payment_id}/capture
    Captures a previously authorised payment.

    Args:
        payment_id:    Razorpay payment ID, e.g. "pay_Nn4T3d8uW9kP2r"
        amount_in_cents: Amount in smallest currency unit (paise for INR).
        currency:      ISO 4217 currency code, default "INR".

    Returns:
        The updated payment object dict from Razorpay.

    Raises:
        RazorpayAPIError on non-2xx response.
    """
    url = f"{RAZORPAY_BASE_URL}/payments/{payment_id}/capture"
    payload = {"amount": amount_in_cents, "currency": currency}

    logger.info(
        "[Razorpay] POST %s  payload=%s", url, payload
    )

    resp = requests.post(
        url,
        auth=_auth(),
        json=payload,
        timeout=DEFAULT_TIMEOUT_S,
    )

    logger.info(
        "[Razorpay] capture_payment(%s, %d) → HTTP %d body=%s",
        payment_id, amount_in_cents, resp.status_code,
        resp.text[:300],   # truncate for log safety
    )

    if resp.ok:
        return resp.json()

    raise RazorpayAPIError(resp.status_code, resp.json())


def retry_payment_with_fallback(
    payment_id: str,
    amount_in_cents: int,
) -> Dict[str, Any]:
    """
    High-level helper used by the recovery scheduler.

    1. Fetch the current payment status from Razorpay.
    2. If already captured → idempotent success.
    3. If authorized  → call capture.
    4. If any other status / API error → raise so caller can handle.

    Returns a dict:
        {
          "razorpay_status": "captured" | "authorized" | ...,
          "api_called": True,
          "http_status": 200,
          "razorpay_response": { ...full payment object... }
        }
    """
    result = {
        "api_called": True,
        "payment_id": payment_id,
    }

    try:
        payment = fetch_payment(payment_id)
        rzp_status = payment.get("status", "unknown")
        result["razorpay_status"] = rzp_status
        result["http_status"] = 200
        result["razorpay_response"] = payment

        if rzp_status == "captured":
            # Already done — idempotent
            logger.info("[Razorpay] Payment %s already captured.", payment_id)
            return result

        if rzp_status == "authorized":
            capture_resp = capture_payment(payment_id, amount_in_cents)
            result["razorpay_status"] = capture_resp.get("status", "captured")
            result["razorpay_response"] = capture_resp
            logger.info("[Razorpay] Captured payment %s successfully.", payment_id)
            return result

        # Payment is in a non-recoverable state (e.g. failed, refunded)
        raise RazorpayAPIError(
            422,
            {
                "error": {
                    "code": "BAD_REQUEST_ERROR",
                    "description": f"Payment {payment_id} is in non-retryable status: {rzp_status}",
                }
            },
        )

    except RazorpayAPIError:
        raise
    except requests.exceptions.RequestException as exc:
        logger.error("[Razorpay] Network error for %s: %s", payment_id, exc)
        raise RazorpayAPIError(0, {"error": {"description": str(exc)}}) from exc
