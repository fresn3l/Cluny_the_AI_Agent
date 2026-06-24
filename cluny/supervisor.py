"""Intent routing supervisor — one entrypoint, multiple backends."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from cluny.agent import run_agent
from cluny.config import Settings
from cluny.query import rag_answer

Route = Literal["ask", "knowledge_agent", "tasks_agent", "calendar"]

_TASK_RE = re.compile(
    r"\b(task|todo|to-do|due|deadline|remind|complete|finish)\b", re.I
)
_CALENDAR_RE = re.compile(
    r"\b(calendar|meeting|schedule|appointment|event|ics)\b", re.I
)
_KNOWLEDGE_RE = re.compile(
    r"\b(notes?|paper|article|indexed|brain|document|journal|remember|who said|what did)\b",
    re.I,
)


@dataclass(frozen=True)
class SupervisorResult:
    route: Route
    answer: str
    tool_calls: list[str]


def classify_intent(question: str) -> Route:
    q = question.strip()
    if _CALENDAR_RE.search(q):
        return "calendar"
    if _TASK_RE.search(q):
        return "tasks_agent"
    if _KNOWLEDGE_RE.search(q):
        return "knowledge_agent"
    return "ask"


def run_chat(
    question: str,
    *,
    settings: Settings | None = None,
) -> SupervisorResult:
    settings = settings or Settings.from_env()
    route = classify_intent(question)

    if route == "calendar":
        try:
            from cluny.calendar_db import connect as cal_connect, list_upcoming

            conn = cal_connect(settings)
            events = list_upcoming(conn, limit=10)
            conn.close()
            if not events:
                return SupervisorResult(
                    route=route,
                    answer="No calendar events imported yet. Use `cluny calendar import file.ics`.",
                    tool_calls=[],
                )
            lines = [f"- {e.summary} ({e.start_at})" for e in events]
            return SupervisorResult(
                route=route,
                answer="Upcoming events:\n" + "\n".join(lines),
                tool_calls=[],
            )
        except Exception:  # noqa: BLE001
            return SupervisorResult(
                route=route,
                answer="Calendar is not available. Import events with `cluny calendar import`.",
                tool_calls=[],
            )

    if route == "tasks_agent":
        result = run_agent(question, settings=settings, mode="tasks")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    if route == "knowledge_agent":
        result = run_agent(question, settings=settings, mode="knowledge")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    rag = rag_answer(question, settings=settings)
    return SupervisorResult(route="ask", answer=rag.answer, tool_calls=[])
