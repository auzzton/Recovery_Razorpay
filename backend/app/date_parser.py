"""
Natural Language Promise-Date Extractor
Uses `dateparser` to parse free-text customer replies like:
  - "Pay on Friday"
  - "Will settle tomorrow"
  - "Send money next week"
  - "Paying in 3 days"

Returns a timezone-aware UTC datetime, always preferred in the future.
Falls back to now + 3 days if no date expression is found.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Lazily imported so the app still starts even if dateparser is not yet installed
try:
    import dateparser
    import dateparser.search
    _DATEPARSER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DATEPARSER_AVAILABLE = False
    logger.warning("dateparser not installed — falling back to +3 day default promise date")


_DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": True,
    "TO_TIMEZONE": "UTC",
    "PREFER_DAY_OF_MONTH": "first",
}


def extract_promise_date(text: str) -> Optional[datetime]:
    """
    Extract the first future date/time from a natural-language string.

    Args:
        text: Raw customer message, e.g. "I'll pay on Friday evening".

    Returns:
        A timezone-aware UTC datetime representing the promised payment date,
        or None if nothing could be parsed.
    """
    if not _DATEPARSER_AVAILABLE or not text:
        return None

    try:
        # search_dates finds date expressions embedded in free text
        results = dateparser.search.search_dates(
            text,
            languages=["en", "hi"],
            settings=_DATEPARSER_SETTINGS,
        )
        if results:
            # results is a list of (matched_string, datetime) tuples
            _, parsed_dt = results[0]

            # Ensure it is in the future (search_dates can still return past dates)
            now_utc = datetime.now(timezone.utc)
            if parsed_dt <= now_utc:
                # Advance by 7 days to keep it a future promise (handles "Friday" when today is Friday)
                parsed_dt = parsed_dt + timedelta(days=7)

            logger.info("Parsed promise date '%s' → %s", text, parsed_dt.isoformat())
            return parsed_dt

    except Exception as exc:  # noqa: BLE001
        logger.warning("dateparser failed for text=%r: %s", text, exc)

    return None


def get_promise_date(text: str) -> str:
    """
    Public helper that always returns an ISO 8601 UTC string.
    Falls back to now + 3 days when no date can be extracted.

    Args:
        text: Customer message.

    Returns:
        ISO 8601 UTC datetime string (e.g. "2026-08-29T18:00:00+00:00").
    """
    now_utc = datetime.now(timezone.utc)
    fallback = (now_utc + timedelta(days=3)).isoformat()

    parsed = extract_promise_date(text)
    if parsed is None:
        logger.info("No date found in '%s', defaulting to +3 days: %s", text, fallback)
        return fallback

    return parsed.isoformat()
