"""Structured Kosistenz life context for Cluny brain routes.

Kosistenz sends a full life snapshot as context_json. We must not drop unknown
keys — week answers come from that snapshot, not from Cluny tasks/calendar SQLite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_KOSISTENZ_INSTRUCTION = (
    "Never pick HH:MM clock times. Do not treat Cluny tasks.sqlite or "
    "calendar.sqlite as the live to-do list or week. Kosistenz commits the week; "
    "you propose work and answer from this snapshot plus indexed notes."
)

LIFE_HTTP_URL = "http://127.0.0.1:18741/api/cluny/life"
DEFAULT_SNAPSHOT_PATH = (
    Path.home() / "Library" / "Application Support" / "ToDo" / "cluny_life_snapshot.json"
)


class DeadlineTodo(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    due: str | None = None


class CalendarEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    start: str | None = None
    end: str | None = None


class GoalProgress(BaseModel):
    model_config = ConfigDict(extra="allow")

    goal: str
    percent: float | None = None


class AnalyticsSnapshot(BaseModel):
    """Weekly or rolling analytics Kosistenz sends with Ask/Propose."""

    model_config = ConfigDict(extra="allow")

    period: str | None = None
    tasks_completed: int | None = None
    tasks_slipped: int | None = None
    focus_hours: float | None = None
    journal_streak_days: int | None = None
    goal_progress: list[GoalProgress] = Field(default_factory=list)


class KosistenzContext(BaseModel):
    """Typed + open context Kosistenz sends with chat/ask/propose.

    Extra keys from the life snapshot (work, calendar.days, briefs, …) are kept.
    """

    model_config = ConfigDict(extra="allow")

    instruction: str | None = None
    date: str | None = None
    week_start: str | None = None
    week_end: str | None = None
    deadline_todos: list[DeadlineTodo] = Field(default_factory=list)
    events_today: list[CalendarEvent] = Field(default_factory=list)
    weekly_goals: list[str] = Field(default_factory=list)
    analytics: AnalyticsSnapshot | None = None
    notes: str | None = None
    journal: Any | None = None
    work: Any | None = None
    calendar: Any | None = None
    workouts: Any | None = None
    workout_plan: Any | None = None
    goals: Any | None = None
    briefs: Any | None = None
    todos_today: Any | None = None
    overdue: Any | None = None
    backlog: Any | None = None
    unplaced: Any | None = None
    free_minutes: Any | None = None


def context_as_dict(raw: Any) -> dict[str, Any] | None:
    """Normalize context_json to a plain dict (extras preserved)."""
    if raw is None:
        return None
    if isinstance(raw, KosistenzContext):
        return raw.model_dump(exclude_none=False)
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.startswith("{"):
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        return None
    return None


def parse_kosistenz_context(raw: Any) -> KosistenzContext | None:
    data = context_as_dict(raw)
    if data is None:
        return None
    return KosistenzContext.model_validate(data)


def _fmt_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        title = item.get("title") or item.get("name") or item.get("summary") or ""
        due = item.get("due") or item.get("due_at") or item.get("due_date")
        status = item.get("status")
        bits = [str(title).strip()] if title else [json.dumps(item, ensure_ascii=False)[:200]]
        if due:
            bits.append(f"due {due}")
        if status:
            bits.append(str(status))
        return " — ".join(bits)
    return str(item)


def _fmt_list(label: str, value: Any, *, limit: int = 12) -> list[str]:
    if value is None:
        return []
    lines = [f"{label}:"]
    if isinstance(value, list):
        if not value:
            lines.append("- (none)")
            return lines
        for item in value[:limit]:
            lines.append(f"- {_fmt_item(item)}")
        if len(value) > limit:
            lines.append(f"- …and {len(value) - limit} more")
        return lines
    if isinstance(value, dict):
        lines.append(json.dumps(value, ensure_ascii=False)[:1200])
        return lines
    lines.append(str(value))
    return lines


def _fmt_journal(value: Any) -> list[str]:
    if value is None:
        return []
    lines = ["Journal (recent):"]
    if isinstance(value, str):
        text = value.strip()
        if len(text) > 4000:
            text = text[:3999] + "…"
        lines.append(text)
        return lines
    if isinstance(value, list):
        for entry in value[:5]:
            if isinstance(entry, dict):
                title = entry.get("title") or entry.get("date") or "entry"
                body = entry.get("content") or entry.get("text") or ""
                lines.append(f"### {title}")
                body_s = str(body).strip()
                if len(body_s) > 1500:
                    body_s = body_s[:1499] + "…"
                if body_s:
                    lines.append(body_s)
            else:
                lines.append(str(entry)[:800])
        return lines
    if isinstance(value, dict):
        content = value.get("content") or value.get("text") or json.dumps(value)
        text = str(content).strip()
        if len(text) > 4000:
            text = text[:3999] + "…"
        lines.append(text)
        return lines
    lines.append(str(value)[:2000])
    return lines


def _fmt_calendar(value: Any) -> list[str]:
    if value is None:
        return []
    lines = ["Calendar:"]
    if isinstance(value, dict):
        days = value.get("days")
        if isinstance(days, list):
            for day in days[:7]:
                if not isinstance(day, dict):
                    lines.append(f"- {day}")
                    continue
                date = day.get("date") or "?"
                hard = day.get("hard_events") or day.get("events") or []
                placed = day.get("placed") or day.get("blocks") or []
                unplaced = day.get("unplaced") or []
                lines.append(f"Day {date}:")
                if hard:
                    lines.append("  Hard events:")
                    for e in hard[:8]:
                        lines.append(f"  - {_fmt_item(e)}")
                if placed:
                    lines.append("  Placed blocks:")
                    for e in placed[:8]:
                        lines.append(f"  - {_fmt_item(e)}")
                if unplaced:
                    lines.append("  Unplaced:")
                    for e in unplaced[:8]:
                        lines.append(f"  - {_fmt_item(e)}")
            return lines
        lines.append(json.dumps(value, ensure_ascii=False)[:1500])
        return lines
    if isinstance(value, list):
        return _fmt_list("Calendar", value)
    lines.append(str(value)[:800])
    return lines


def format_analytics_snapshot(analytics: AnalyticsSnapshot | dict[str, Any]) -> str:
    if isinstance(analytics, dict):
        analytics = AnalyticsSnapshot.model_validate(analytics)
    lines: list[str] = ["Analytics snapshot:"]
    if analytics.period:
        lines.append(f"Period: {analytics.period}")
    if analytics.tasks_completed is not None:
        lines.append(f"Tasks completed: {analytics.tasks_completed}")
    if analytics.tasks_slipped is not None:
        lines.append(f"Tasks slipped: {analytics.tasks_slipped}")
    if analytics.focus_hours is not None:
        lines.append(f"Focus hours: {analytics.focus_hours}")
    if analytics.journal_streak_days is not None:
        lines.append(f"Journal streak (days): {analytics.journal_streak_days}")
    if analytics.goal_progress:
        lines.append("Goal progress:")
        for g in analytics.goal_progress:
            pct = f" ({g.percent}%)" if g.percent is not None else ""
            lines.append(f"- {g.goal}{pct}")
    return "\n".join(lines)


def format_kosistenz_context(ctx: KosistenzContext | dict[str, Any]) -> str:
    """Format the full life snapshot for the model prompt."""
    data = context_as_dict(ctx) or {}
    lines: list[str] = []

    instruction = str(data.get("instruction") or "").strip() or DEFAULT_KOSISTENZ_INSTRUCTION
    lines.append(f"Instruction: {instruction}")

    if data.get("date"):
        lines.append(f"Date: {data['date']}")
    if data.get("week_start") or data.get("week_end"):
        lines.append(
            f"Week: {data.get('week_start') or '?'} → {data.get('week_end') or '?'}"
        )

    weekly = data.get("weekly_goals") or []
    if weekly:
        lines.append("Weekly goals:")
        lines.extend(f"- {g}" for g in weekly)

    analytics = data.get("analytics")
    if analytics:
        lines.append(format_analytics_snapshot(analytics))

    lines.extend(_fmt_list("Todos today", data.get("todos_today")))
    lines.extend(_fmt_list("Overdue", data.get("overdue")))
    lines.extend(_fmt_list("Deadline to-dos", data.get("deadline_todos")))
    lines.extend(_fmt_list("Backlog", data.get("backlog")))
    lines.extend(_fmt_list("Unplaced work", data.get("unplaced")))
    lines.extend(_fmt_list("Events today", data.get("events_today")))

    if data.get("free_minutes") is not None:
        lines.append(f"Free minutes (today/week context): {data['free_minutes']}")

    work = data.get("work")
    if work is not None:
        if isinstance(work, dict):
            for key in ("today", "overdue", "backlog", "notes", "unplaced"):
                if key in work:
                    lines.extend(_fmt_list(f"Work · {key}", work.get(key)))
        else:
            lines.extend(_fmt_list("Work", work))

    lines.extend(_fmt_calendar(data.get("calendar")))
    lines.extend(_fmt_list("Goals", data.get("goals")))
    lines.extend(_fmt_list("Workouts", data.get("workouts")))
    if data.get("workout_plan") is not None:
        lines.extend(_fmt_list("Workout plan", data.get("workout_plan"), limit=8))
    if data.get("briefs") is not None:
        lines.extend(_fmt_list("Briefs", data.get("briefs"), limit=6))
    lines.extend(_fmt_journal(data.get("journal")))

    if data.get("notes"):
        lines.append(f"Notes: {data['notes']}")

    # Any remaining top-level keys (forward compatible)
    known = {
        "instruction",
        "date",
        "week_start",
        "week_end",
        "weekly_goals",
        "analytics",
        "todos_today",
        "overdue",
        "deadline_todos",
        "backlog",
        "unplaced",
        "events_today",
        "free_minutes",
        "work",
        "calendar",
        "goals",
        "workouts",
        "workout_plan",
        "briefs",
        "journal",
        "notes",
    }
    extras = {k: v for k, v in data.items() if k not in known and v is not None}
    for key, value in extras.items():
        lines.extend(_fmt_list(f"Extra · {key}", value, limit=6))

    return "\n".join(line for line in lines if line is not None)


def snapshot_path() -> Path:
    override = (os.environ.get("CLUNY_KOSISTENZ_SNAPSHOT") or "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_SNAPSHOT_PATH


def fetch_life_snapshot_http(*, timeout: float = 0.4) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(LIFE_HTTP_URL)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def read_life_snapshot_file(path: Path | None = None) -> dict[str, Any] | None:
    p = path or snapshot_path()
    try:
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def load_life_snapshot() -> dict[str, Any] | None:
    """Prefer live HTTP while Kosistenz is open; else snapshot file."""
    return fetch_life_snapshot_http() or read_life_snapshot_file()


def resolve_context_json(
    context_json: KosistenzContext | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Use provided context_json, or load the Kosistenz life snapshot if missing."""
    data = context_as_dict(context_json)
    if data:
        return data
    return load_life_snapshot()


def merge_context(
    *,
    context: str | None = None,
    context_json: KosistenzContext | dict[str, Any] | None = None,
    resolve_missing: bool = True,
) -> str | None:
    """Combine free-text and structured Kosistenz context for prompts."""
    parts: list[str] = []
    data = resolve_context_json(context_json) if resolve_missing else context_as_dict(context_json)
    if data:
        block = format_kosistenz_context(data)
        if block:
            parts.append(block)
    if context and context.strip():
        parts.append(context.strip())
    if not parts:
        return None
    return "\n\n".join(parts)


def format_chat_question(
    question: str,
    context: str | None = None,
    *,
    context_json: KosistenzContext | dict[str, Any] | None = None,
    history_prefix: str | None = None,
) -> str:
    """Merge Kosistenz-supplied context (or life snapshot) and optional session history."""
    q = question.strip()
    resolved = resolve_context_json(context_json)
    merged_ctx = merge_context(
        context=context,
        context_json=resolved,
        resolve_missing=False,
    )
    if merged_ctx:
        q = f"Context from Kosistenz:\n{merged_ctx}\n\nQuestion:\n{q}"
    if history_prefix:
        q = history_prefix + q
    return q
