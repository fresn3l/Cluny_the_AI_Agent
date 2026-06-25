"""Parse human-friendly due dates for tasks."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_REL_DAYS = re.compile(r"^\+(\d+)d$", re.I)


def parse_due(raw: str | None) -> str | None:
    """Return ISO8601 UTC string or None."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    lower = text.lower()
    now = datetime.now(timezone.utc)

    if lower == "today":
        dt = now.replace(hour=23, minute=59, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if lower == "tomorrow":
        dt = (now + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    m = _REL_DAYS.match(lower)
    if m:
        days = int(m.group(1))
        dt = (now + timedelta(days=days)).replace(hour=23, minute=59, second=0, microsecond=0)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        from dateutil import parser as date_parser

        dt = date_parser.parse(text, default=now)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return text
