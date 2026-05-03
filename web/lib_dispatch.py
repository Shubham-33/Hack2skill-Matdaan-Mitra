"""URL-spec dispatch helpers — Calendar, WhatsApp, Maps, ECI deeplinks.

These follow the hackathon-playbook pattern of using URL templates instead of
OAuth flows. Each function returns a URL that opens the target service in the
user's already-logged-in tab. No tokens, no scopes, no consent screens.

The helpers here are pure functions (no I/O, no global state), which makes
them trivially testable and reusable.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Final

CALENDAR_URL_BASE: Final[str] = "https://calendar.google.com/calendar/render"
WHATSAPP_URL_BASE: Final[str] = "https://wa.me/"
MAPS_URL_BASE: Final[str] = "https://maps.google.com/"
ECI_VOTER_PORTAL: Final[str] = "https://electoralsearch.eci.gov.in/"

DEFAULT_EVENT_DURATION_HOURS: Final[int] = 2


def to_calendar_format(iso_or_date: str) -> str:
    """Convert 'YYYY-MM-DD' or full ISO 8601 → 'YYYYMMDDTHHMMSSZ' (Calendar URL format).

    Date-only inputs are treated as 09:00 IST (start of polling). Full ISO 8601
    timestamps with timezone offsets are converted to UTC.

    :param iso_or_date: A date string in either format.
    :raises ValueError: When the input doesn't parse as ISO 8601.
    """
    s = iso_or_date.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        # Date-only: assume 09:00 IST start of polling
        dt = datetime.strptime(s + "T09:00:00+05:30", "%Y-%m-%dT%H:%M:%S%z")
    else:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def calendar_event_url(*, title: str, start: str, end: str | None = None,
                       details: str = "", location: str = "") -> str:
    """Build a Google Calendar 'render' URL — opens in user's logged-in tab.

    :param title: Event title (e.g. "Vote together — Family Squad").
    :param start: ISO 8601 timestamp or YYYY-MM-DD date string.
    :param end: Optional end time. Defaults to start + 2 hours.
    :param details: Free-text description shown in the event body.
    :param location: Free-text location (e.g. polling station address).
    :returns: A URL that, when opened, prefills the Calendar event-create dialog.
    """
    start_cal = to_calendar_format(start)
    if end:
        end_cal = to_calendar_format(end)
    else:
        end_dt = (
            datetime.strptime(start_cal, "%Y%m%dT%H%M%SZ")
            + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS)
        )
        end_cal = end_dt.strftime("%Y%m%dT%H%M%SZ")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_cal}/{end_cal}",
        "details": details,
        "location": location,
    }
    return CALENDAR_URL_BASE + "?" + urllib.parse.urlencode(
        {k: v for k, v in params.items() if v}
    )


def whatsapp_share_url(text: str) -> str:
    """Open WhatsApp / WhatsApp Web with prefilled message text. No auth."""
    return WHATSAPP_URL_BASE + "?text=" + urllib.parse.quote(text)


def maps_search_url(query: str) -> str:
    """Open Google Maps with a prefilled search query. No API key, no auth."""
    return MAPS_URL_BASE + "?q=" + urllib.parse.quote(query)


def eci_registration_url() -> str:
    """ECI's own voter-search portal — user enters their EPIC ID directly there.

    This is deliberately a deeplink rather than a form on our site. The EPIC ID
    is sensitive (PII tied to electoral roll) and we choose to never have it touch
    our servers. The user takes it directly to the source of truth.
    """
    return ECI_VOTER_PORTAL
