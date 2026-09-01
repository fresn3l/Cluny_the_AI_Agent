"""Structured context bundles for Kosistenz day/meeting views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cluny.calendar_db import EventRow, connect as cal_connect, events_on_date, list_upcoming
from cluny.config import Settings
from cluny.dates import parse_due
from cluny.query import retrieve
from cluny.tasks_db import TaskRow, connect as tasks_connect, list_tasks


@dataclass(frozen=True)
class Snippet:
    label: str
    text: str
    score: float


def _task_dict(t: TaskRow) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "due_at": t.due_at,
        "notes": t.notes,
        "project_id": t.project_id,
        "recurrence": t.recurrence,
        "external_id": t.external_id,
    }


def _event_dict(e: EventRow) -> dict[str, Any]:
    return {
        "id": e.id,
        "summary": e.summary,
        "start_at": e.start_at,
        "end_at": e.end_at,
        "location": e.location,
    }


def _snippets_for_query(query: str, settings: Settings, *, k: int = 5) -> list[Snippet]:
    try:
        chunks = retrieve(query, k=k, settings=settings, fts_only=True)
    except Exception:  # noqa: BLE001
        return []
    return [
        Snippet(
            label=ch.label,
            text=ch.text[:500],
            score=ch.score,
        )
        for ch in chunks
    ]


def build_day_context(settings: Settings, date: str) -> dict[str, Any]:
    """Tasks + events for a calendar day (no LLM)."""
    parsed = parse_due(date) or date
    day_prefix = parsed[:10] if len(parsed) >= 10 else date[:10]

    tasks_conn = tasks_connect(settings)
    all_open = list_tasks(tasks_conn, status="open")
    tasks_conn.close()
    day_tasks = [
        t for t in all_open
        if t.due_at and t.due_at.startswith(day_prefix)
    ]

    cal_conn = cal_connect(settings)
    events = events_on_date(cal_conn, day_prefix)
    cal_conn.close()

    return {
        "date": day_prefix,
        "tasks": [_task_dict(t) for t in day_tasks],
        "events": [_event_dict(e) for e in events],
        "snippets": [],
    }


def build_meeting_context(
    settings: Settings,
    *,
    title: str,
    date: str | None = None,
    snippet_k: int = 5,
) -> dict[str, Any]:
    """Events, related tasks, and note snippets for meeting prep."""
    title = title.strip()
    events: list[EventRow] = []
    cal_conn = cal_connect(settings)
    if date:
        events = events_on_date(cal_conn, date)
    if not events:
        upcoming = list_upcoming(cal_conn, limit=30)
        title_lower = title.lower()
        events = [e for e in upcoming if title_lower in e.summary.lower()]
    cal_conn.close()

    tasks_conn = tasks_connect(settings)
    open_tasks = list_tasks(tasks_conn, status="open")
    tasks_conn.close()
    title_lower = title.lower()
    related = [
        t for t in open_tasks
        if title_lower in t.title.lower()
        or (t.notes and title_lower in t.notes.lower())
    ]

    snippets = _snippets_for_query(title, settings, k=snippet_k)

    return {
        "title": title,
        "date": date,
        "events": [_event_dict(e) for e in events],
        "tasks": [_task_dict(t) for t in related],
        "snippets": [
            {"label": s.label, "text": s.text, "score": s.score}
            for s in snippets
        ],
    }
