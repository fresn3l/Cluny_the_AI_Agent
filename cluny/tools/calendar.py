"""Read-only calendar tools for the agent."""

from __future__ import annotations

from typing import Any

from cluny.calendar_db import connect, events_on_date, list_upcoming
from cluny.config import Settings
from cluny.tools.registry import Tool


def _list_events(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    limit = int(args.get("limit", 20))
    conn = connect(settings)
    rows = list_upcoming(conn, limit=limit)
    conn.close()
    return {
        "events": [
            {
                "summary": e.summary,
                "start_at": e.start_at,
                "end_at": e.end_at,
                "location": e.location,
            }
            for e in rows
        ]
    }


def _events_on_date(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    date_str = str(args.get("date", "")).strip()
    if not date_str:
        return {"error": "date is required (YYYY-MM-DD or natural language)"}
    conn = connect(settings)
    rows = events_on_date(conn, date_str)
    conn.close()
    return {
        "date": date_str,
        "events": [
            {"summary": e.summary, "start_at": e.start_at, "location": e.location}
            for e in rows
        ],
    }


def build_calendar_tools(settings: Settings) -> list[Tool]:
    return [
        Tool(
            name="list_events",
            description="List upcoming calendar events (read-only, from imported ICS).",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max events (default 20)"},
                },
            },
            handler=lambda args: _list_events(args, settings),
        ),
        Tool(
            name="events_on_date",
            description="List calendar events on a specific date.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date like 2026-06-25 or Thursday"},
                },
                "required": ["date"],
            },
            handler=lambda args: _events_on_date(args, settings),
        ),
    ]
