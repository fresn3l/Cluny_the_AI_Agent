"""Intent routing supervisor — one entrypoint, multiple backends."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from cluny.agent import run_agent
from cluny.config import Settings
from cluny.ollama_client import OllamaClient
from cluny.query import rag_answer

Route = Literal["ask", "knowledge_agent", "tasks_agent", "calendar", "planner"]

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
_PLANNER_RE = re.compile(
    r"\b(and then|after that|also (add|create)|summarize .+ and (add|create))\b",
    re.I,
)

ROUTER_SYSTEM = (
    "Classify the user message into exactly one route. Reply with ONLY one word:\n"
    "ask — general question answerable from retrieved notes in one shot\n"
    "knowledge_agent — needs searching indexed notes with tools\n"
    "tasks_agent — about to-do list, deadlines, completing tasks\n"
    "calendar — meetings, schedule, appointments\n"
    "planner — needs BOTH notes search AND task action (compound request)\n"
)


@dataclass(frozen=True)
class SupervisorResult:
    route: Route
    answer: str
    tool_calls: list[str]


def classify_intent_regex(question: str) -> Route:
    q = question.strip()
    if _PLANNER_RE.search(q) and (_TASK_RE.search(q) or _KNOWLEDGE_RE.search(q)):
        return "planner"
    if _CALENDAR_RE.search(q):
        return "calendar"
    if _TASK_RE.search(q):
        return "tasks_agent"
    if _KNOWLEDGE_RE.search(q):
        return "knowledge_agent"
    return "ask"


def classify_intent_llm(question: str, settings: Settings) -> Route:
    ollama = OllamaClient(settings)
    try:
        raw = ollama.chat(system=ROUTER_SYSTEM, user=question.strip()).strip().lower()
    except Exception:  # noqa: BLE001
        return classify_intent_regex(question)
    for route in ("planner", "calendar", "tasks_agent", "knowledge_agent", "ask"):
        if route in raw.replace(" ", "_") or route.replace("_", " ") in raw:
            return route  # type: ignore[return-value]
    return classify_intent_regex(question)


def classify_intent(question: str, settings: Settings | None = None) -> Route:
    settings = settings or Settings.load()
    if settings.supervisor_mode == "regex":
        return classify_intent_regex(question)
    return classify_intent_llm(question, settings)


def _calendar_answer(settings: Settings) -> SupervisorResult:
    try:
        from cluny.calendar_db import connect as cal_connect, list_upcoming

        conn = cal_connect(settings)
        events = list_upcoming(conn, limit=10)
        conn.close()
        if not events:
            return SupervisorResult(
                route="calendar",
                answer="No calendar events imported yet. Use `cluny calendar import file.ics`.",
                tool_calls=[],
            )
        lines = [f"- {e.summary} ({e.start_at})" for e in events]
        return SupervisorResult(
            route="calendar",
            answer="Upcoming events:\n" + "\n".join(lines),
            tool_calls=[],
        )
    except Exception:  # noqa: BLE001
        return SupervisorResult(
            route="calendar",
            answer="Calendar is not available. Import events with `cluny calendar import`.",
            tool_calls=[],
        )


def run_chat(
    question: str,
    *,
    settings: Settings | None = None,
) -> SupervisorResult:
    settings = settings or Settings.load()
    route = classify_intent(question, settings)

    if route == "calendar":
        return _calendar_answer(settings)

    if route == "planner":
        result = run_agent(question, settings=settings, mode="planner")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    if route == "tasks_agent":
        result = run_agent(question, settings=settings, mode="tasks")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    if route == "knowledge_agent":
        result = run_agent(question, settings=settings, mode="knowledge")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    rag = rag_answer(question, settings=settings)
    return SupervisorResult(route="ask", answer=rag.answer, tool_calls=[])
