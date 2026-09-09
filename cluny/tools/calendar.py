"""Read-only week tools — prefer Kosistenz snapshot over Cluny calendar.sqlite."""

from __future__ import annotations

from typing import Any

from cluny.config import Settings
from cluny.kosistenz_context import (
    format_kosistenz_context,
    load_life_snapshot,
    resolve_context_json,
)
from cluny.tools.registry import Tool


def _week_from_snapshot(args: dict[str, Any], settings: Settings) -> dict[str, Any]:  # noqa: ARG001
    """Return the live week from Kosistenz snapshot/context — not calendar.sqlite."""
    data = load_life_snapshot()
    if not data:
        return {
            "ok": False,
            "source": None,
            "message": (
                "No Kosistenz life snapshot available. "
                "Answer from indexed notes only — do not invent a week from "
                "Cluny calendar.sqlite or tasks.sqlite."
            ),
            "week": None,
        }
    return {
        "ok": True,
        "source": "kosistenz_snapshot",
        "message": (
            "This is the Kosistenz life week. Do not write placements or clock times."
        ),
        "formatted": format_kosistenz_context(data),
        "date": data.get("date"),
        "todos_today": data.get("todos_today"),
        "overdue": data.get("overdue"),
        "unplaced": data.get("unplaced"),
        "free_minutes": data.get("free_minutes"),
        "events_today": data.get("events_today"),
    }


def _events_on_date_snapshot(args: dict[str, Any], settings: Settings) -> dict[str, Any]:  # noqa: ARG001
    date_str = str(args.get("date", "")).strip()
    if not date_str:
        return {"error": "date is required (YYYY-MM-DD)"}
    data = resolve_context_json(None) or load_life_snapshot()
    if not data:
        return {
            "ok": False,
            "date": date_str,
            "message": (
                "No Kosistenz snapshot. Do not use Cluny calendar.sqlite as the live week."
            ),
            "events": [],
        }
    days = []
    cal = data.get("calendar")
    if isinstance(cal, dict) and isinstance(cal.get("days"), list):
        days = cal["days"]
    matched = []
    for day in days:
        if not isinstance(day, dict):
            continue
        if str(day.get("date") or "")[:10] == date_str[:10]:
            matched.append(day)
    return {
        "ok": True,
        "date": date_str,
        "source": "kosistenz_snapshot",
        "days": matched,
        "message": "From Kosistenz snapshot only. Do not place or import ICS as live calendar.",
    }


def build_calendar_tools(settings: Settings) -> list[Tool]:
    """Snapshot-first week tools (replaces Cluny calendar.sqlite for agent modes)."""
    return [
        Tool(
            name="week_from_snapshot",
            description=(
                "Read the live Kosistenz week (todos today, overdue, unplaced, free time). "
                "Prefer this over any Cluny calendar.sqlite. Read-only."
            ),
            parameters={"type": "object", "properties": {}},
            handler=lambda args: _week_from_snapshot(args, settings),
        ),
        Tool(
            name="events_on_date",
            description=(
                "List Kosistenz calendar day details from the life snapshot. "
                "Not Cluny calendar.sqlite."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date YYYY-MM-DD",
                    },
                },
                "required": ["date"],
            },
            handler=lambda args: _events_on_date_snapshot(args, settings),
        ),
    ]
