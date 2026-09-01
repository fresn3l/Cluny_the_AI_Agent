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


class KosistenzContext(BaseModel):
    """Typed context Kosistenz sends with chat/ask/propose requests."""

    date: str | None = None
    deadline_todos: list[DeadlineTodo] = Field(default_factory=list)
    events_today: list[CalendarEvent] = Field(default_factory=list)
    weekly_goals: list[str] = Field(default_factory=list)
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


def format_kosistenz_context(ctx: KosistenzContext) -> str:
    lines: list[str] = []
    if ctx.date:
        lines.append(f"Date: {ctx.date}")
    if ctx.weekly_goals:
        lines.append("Weekly goals:")
        lines.extend(f"- {g}" for g in ctx.weekly_goals)
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
