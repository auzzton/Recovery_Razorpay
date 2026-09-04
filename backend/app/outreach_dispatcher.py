"""
Outreach Dispatcher
~~~~~~~~~~~~~~~~~~~
Automated channel-selection and message dispatch for payment recovery.

Priority:
  1. Email (Resend API or SMTP) — if customer_email is present
  2. WhatsApp (Twilio Sandbox)  — fallback if email is missing
  3. SMS (Twilio standard)      — fallback if no WhatsApp sandbox join
  4. SIMULATION                 — no-op log if no credentials configured

Keys are read from environment variables:
  RESEND_API_KEY          → Resend.com API key  (primary email)
  SMTP_HOST               → SMTP server host     (alternative email)
  SMTP_PORT               → SMTP port (default: 587)
  SMTP_USER               → SMTP username
  SMTP_PASSWORD           → SMTP password
  SMTP_FROM               → From address (default: SMTP_USER)
  TWILIO_ACCOUNT_SID      → Twilio Account SID   (WhatsApp / SMS fallback)
  TWILIO_AUTH_TOKEN       → Twilio Auth Token
  TWILIO_FROM_WHATSAPP    → Twilio sandbox number, e.g. +14155238886
  TWILIO_FROM_SMS         → Twilio SMS from number
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Ensure project root is in sys.path when module is loaded directly
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Environment configuration helper getters (dynamically read from env)
# ──────────────────────────────────────────────────────────────────────────────
def _get_resend_api_key(): return os.environ.get("RESEND_API_KEY")
def _get_smtp_host(): return os.environ.get("SMTP_HOST")
def _get_smtp_port(): return int(os.environ.get("SMTP_PORT", "587"))
def _get_smtp_user(): return os.environ.get("SMTP_USER")
def _get_smtp_pass(): return os.environ.get("SMTP_PASSWORD")
def _get_smtp_from(): return os.environ.get("SMTP_FROM", _get_smtp_user())
def _get_twilio_sid(): return os.environ.get("TWILIO_ACCOUNT_SID")
def _get_twilio_token(): return os.environ.get("TWILIO_AUTH_TOKEN")
def _get_twilio_wa_from(): return os.environ.get("TWILIO_FROM_WHATSAPP")
def _get_twilio_sms_from(): return os.environ.get("TWILIO_FROM_SMS")
def _get_resend_from(): return os.environ.get("RESEND_FROM_EMAIL", "RecoveryOS <onboarding@resend.dev>")
if not _get_twilio_wa_from():
    logger.warning(
        "[Outreach] TWILIO_FROM_WHATSAPP env var is not set. "
        "WhatsApp dispatch will fall back to simulation mode."
    )
if _get_resend_from() == "RecoveryOS <onboarding@resend.dev>":
    logger.warning(
        "[Outreach] RESEND_FROM_EMAIL is not set. Using Resend test domain (onboarding@resend.dev). "
        "This will be rejected or land in spam on a real Resend account with a verified domain."
    )


# ──────────────────────────────────────────────────────────────────────────────
# HTML email template builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_html_email(
    customer_name: str,
    amount_rupees: str,
    failure_reason: str,
    payment_url: str,
    body_text: str,
) -> str:
    """Returns a polished, mobile-friendly HTML email for payment recovery."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Payment Recovery Reminder</title>
</head>
<body style="margin:0;padding:0;background:#f4f7fb;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#072654 0%,#1a56db 100%);padding:28px 32px;">
              <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.5px;">
                &#128274; Action Required — Payment Failed
              </h1>
              <p style="margin:6px 0 0;color:rgba(255,255,255,0.75);font-size:13px;">RecoveryOS · Razorpay Revenue Recovery</p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <p style="margin:0 0 16px;font-size:16px;color:#1e293b;">Hi <strong>{customer_name}</strong>,</p>
              <p style="margin:0 0 24px;font-size:15px;color:#475569;line-height:1.6;">{body_text}</p>

              <!-- Amount box -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:24px;">
                <tr>
                  <td style="padding:16px 20px;">
                    <p style="margin:0;font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Amount Due</p>
                    <p style="margin:4px 0 0;font-size:26px;font-weight:700;color:#0f172a;">{amount_rupees}</p>
                    <p style="margin:4px 0 0;font-size:12px;color:#ef4444;">&#9888; Failure: {failure_reason}</p>
                  </td>
                </tr>
              </table>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
                <tr>
                  <td style="background:#1a56db;border-radius:8px;padding:14px 32px;">
                    <a href="{payment_url}" style="color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;display:block;">
                      &#10003;&nbsp; Complete Payment Now
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
                This is an automated recovery message. Reply to this email or click the button above.<br/>
                To stop receiving reminders, reply <strong>STOP</strong>.
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:16px 32px;text-align:center;">
              <p style="margin:0;font-size:11px;color:#94a3b8;">
                Powered by <strong>RecoveryOS</strong> &middot; Razorpay Revenue Recovery &middot; AI-Driven Payment Rescue
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Email senders
# ──────────────────────────────────────────────────────────────────────────────

def _send_via_resend(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str,
) -> dict:
    """Send email via Resend REST API (resend.com)."""
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {_get_resend_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "from": _get_resend_from(),
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "text": plain_body,
        },
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        logger.info("[Outreach] Resend email sent to %s, id=%s", to_email, data.get("id"))
        return {"channel": "EMAIL", "provider": "RESEND", "status": "sent", "provider_id": data.get("id")}
    else:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")


def _send_via_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: str,
) -> dict:
    """Send email via SMTP (Gmail App Password / any SMTP relay)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _get_smtp_from()
    msg["To"]      = to_email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(_get_smtp_host(), _get_smtp_port()) as server:
        server.starttls(context=context)
        server.login(_get_smtp_user(), _get_smtp_pass())
        server.sendmail(_get_smtp_from(), to_email, msg.as_string())

    logger.info("[Outreach] SMTP email sent to %s via %s", to_email, _get_smtp_host())
    return {"channel": "EMAIL", "provider": "SMTP", "status": "sent", "provider_id": None}


# ──────────────────────────────────────────────────────────────────────────────
# WhatsApp / SMS sender (Twilio)
# ──────────────────────────────────────────────────────────────────────────────

def _send_via_twilio(to_phone: str, message: str, use_whatsapp: bool = True) -> dict:
    """Send a WhatsApp or SMS message via Twilio."""
    sid   = _get_twilio_sid()
    token = _get_twilio_token()
    from_number = f"whatsapp:{_get_twilio_wa_from()}" if use_whatsapp else _get_twilio_sms_from()
    to_number   = f"whatsapp:{to_phone}"               if use_whatsapp else to_phone

    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": from_number, "To": to_number, "Body": message},
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        channel = "WHATSAPP" if use_whatsapp else "SMS"
        logger.info("[Outreach] Twilio %s sent to %s, sid=%s", channel, to_phone, data.get("sid"))
        return {"channel": channel, "provider": "TWILIO", "status": "sent", "provider_id": data.get("sid")}
    else:
        raise RuntimeError(f"Twilio API error {resp.status_code}: {resp.text}")


# ──────────────────────────────────────────────────────────────────────────────
# Public interface
# ──────────────────────────────────────────────────────────────────────────────

def send_payment_reminder(
    customer_name: str,
    customer_email: Optional[str],
    customer_phone: Optional[str],
    amount_in_cents: int,
    failure_code: str,
    payment_url: str,
    message_body: str,
    event_id: str,
) -> dict:
    """
    Dispatch a live payment recovery reminder via the best available channel.

    Priority:
      1. Email (Resend → SMTP) — if customer_email is present
      2. WhatsApp (Twilio)     — if customer_phone is present and Twilio is configured
      3. SMS (Twilio)          — secondary Twilio fallback
      4. SIMULATION            — log-only mode when no credentials are present

    Returns a dict describing the channel, provider, and status used.
    """
    amount_rupees    = f"₹{amount_in_cents / 100:,.2f}"
    failure_readable = failure_code.replace("_", " ").title()
    subject          = f"Action Required: Your payment of {amount_rupees} failed — Complete it now"

    html_body = _build_html_email(
        customer_name=customer_name,
        amount_rupees=amount_rupees,
        failure_reason=failure_readable,
        payment_url=payment_url,
        body_text=message_body,
    )

    # ── CHANNEL 1: Email ──────────────────────────────────────────────────────
    if customer_email:
        try:
            if _get_smtp_host() and _get_smtp_user() and _get_smtp_pass():
                return _send_via_smtp(customer_email, subject, html_body, message_body)
            elif _get_resend_api_key():
                return _send_via_resend(customer_email, subject, html_body, message_body)
        except Exception as exc:
            logger.warning(
                "[Outreach] Primary email dispatch failed for %s: %s. Trying WhatsApp fallback.", event_id, exc
            )

    # ── CHANNEL 2: WhatsApp (Twilio) ─────────────────────────────────────────
    if customer_phone and _get_twilio_sid() and _get_twilio_token():
        try:
            return _send_via_twilio(customer_phone, message_body, use_whatsapp=True)
        except Exception as exc:
            logger.warning("[Outreach] WhatsApp fallback failed: %s. Trying SMS.", exc)
            try:
                if _get_twilio_sms_from():
                    return _send_via_twilio(customer_phone, message_body, use_whatsapp=False)
            except Exception as exc2:
                logger.error("[Outreach] SMS fallback also failed: %s", exc2)

    # ── CHANNEL 4: Simulation (log-only) ─────────────────────────────────────
    logger.info(
        "[Outreach][SIMULATION] No live credentials configured. "
        "Would send to email=%s phone=%s  msg='%s...'",
        customer_email, customer_phone, message_body[:80]
    )
    return {
        "channel": "SIMULATION",
        "provider": "NONE",
        "status": "simulated",
        "note": (
            "No RESEND_API_KEY / SMTP credentials / TWILIO credentials found. "
            "Set environment variables to enable live dispatch."
        ),
    }
