"""Structured Kosistenz context for Cluny brain routes."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


class DeadlineTodo(BaseModel):
    title: str
    due: str | None = None


class CalendarEvent(BaseModel):
    title: str
    start: str | None = None
    end: str | None = None


class GoalProgress(BaseModel):
    goal: str
    percent: float | None = None


class AnalyticsSnapshot(BaseModel):
    """Weekly or rolling analytics Kosistenz sends with Ask/Propose."""

    period: str | None = None
    tasks_completed: int | None = None
    tasks_slipped: int | None = None
    focus_hours: float | None = None
    journal_streak_days: int | None = None
    goal_progress: list[GoalProgress] = Field(default_factory=list)


class KosistenzContext(BaseModel):
    """Typed context Kosistenz sends with chat/ask/propose requests."""

    date: str | None = None
    deadline_todos: list[DeadlineTodo] = Field(default_factory=list)
    events_today: list[CalendarEvent] = Field(default_factory=list)
    weekly_goals: list[str] = Field(default_factory=list)
    analytics: AnalyticsSnapshot | None = None
    notes: str | None = None


def parse_kosistenz_context(raw: Any) -> KosistenzContext | None:
    if raw is None:
        return None
    if isinstance(raw, KosistenzContext):
        return raw
    if isinstance(raw, dict):
        return KosistenzContext.model_validate(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.startswith("{"):
            return KosistenzContext.model_validate(json.loads(text))
        return None
    return None


def format_analytics_snapshot(analytics: AnalyticsSnapshot) -> str:
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


def format_kosistenz_context(ctx: KosistenzContext) -> str:
    lines: list[str] = []
    if ctx.date:
        lines.append(f"Date: {ctx.date}")
    if ctx.weekly_goals:
        lines.append("Weekly goals:")
        lines.extend(f"- {g}" for g in ctx.weekly_goals)
    if ctx.analytics:
        lines.append(format_analytics_snapshot(ctx.analytics))
    if ctx.deadline_todos:
        lines.append("Deadline to-dos:")
        for t in ctx.deadline_todos:
            due = f" (due {t.due})" if t.due else ""
            lines.append(f"- {t.title}{due}")
    if ctx.events_today:
        lines.append("Events today:")
        for e in ctx.events_today:
            when = e.start or "?"
            lines.append(f"- {e.title} ({when})")
    if ctx.notes:
        lines.append(f"Notes: {ctx.notes}")
    return "\n".join(lines)


def merge_context(
    *,
    context: str | None = None,
    context_json: KosistenzContext | dict[str, Any] | None = None,
) -> str | None:
    """Combine free-text and structured Kosistenz context."""
    parts: list[str] = []
    parsed = parse_kosistenz_context(context_json)
    if parsed:
        block = format_kosistenz_context(parsed)
        if block:
            parts.append(block)
    if context and context.strip():
        parts.append(context.strip())
    if not parts:
        return None
    return "\n\n".join(parts)
