"""Intent routing supervisor — one entrypoint, multiple backends."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from cluny.agent import run_agent
from cluny.config import Settings
from cluny.kosistenz_context import KosistenzContext, merge_context
from cluny.ollama_client import OllamaClient
from cluny.query import RagSource, rag_answer, rag_answer_stream

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
class SourceCitation:
    label: str
    snippet: str
    doc_path: str | None = None
    chunk_index: int | None = None

    @classmethod
    def from_rag(cls, s: RagSource) -> SourceCitation:
        return cls(
            label=s.label,
            snippet=s.snippet,
            doc_path=s.doc_path,
            chunk_index=s.chunk_index,
        )

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "label": self.label,
            "snippet": self.snippet,
            "doc_path": self.doc_path,
            "chunk_index": self.chunk_index,
        }


@dataclass(frozen=True)
class SupervisorResult:
    route: Route
    answer: str
    tool_calls: list[str]
    sources: tuple[SourceCitation, ...] = ()


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


def format_chat_question(
    question: str,
    context: str | None = None,
    *,
    context_json: KosistenzContext | dict | None = None,
    history_prefix: str | None = None,
) -> str:
    """Merge Kosistenz-supplied context and optional session history."""
    q = question.strip()
    merged_ctx = merge_context(context=context, context_json=context_json)
    if merged_ctx:
        q = f"Context from Kosistenz:\n{merged_ctx}\n\nQuestion:\n{q}"
    if history_prefix:
        q = history_prefix + q
    return q


def _result_from_rag(route: Route, rag) -> SupervisorResult:
    return SupervisorResult(
        route=route,
        answer=rag.answer,
        tool_calls=[],
        sources=tuple(SourceCitation.from_rag(s) for s in rag.sources),
    )


def _calendar_answer(
    settings: Settings,
    question: str,
    *,
    collection_name: str | None = None,
) -> SupervisorResult:
    if settings.kosistenz_journal_dir:
        rag = rag_answer(question, settings=settings, collection_name=collection_name)
        prefix = (
            "Calendar and scheduling live in Kosistenz. Include events and deadlines "
            "in your message — answering from that context and indexed notes.\n\n"
        )
        return SupervisorResult(
            route="calendar",
            answer=prefix + rag.answer,
            tool_calls=[],
            sources=tuple(SourceCitation.from_rag(s) for s in rag.sources),
        )
    try:
        from cluny.calendar_db import connect as cal_connect, list_upcoming

        conn = cal_connect(settings)
        events = list_upcoming(conn, limit=10)
        conn.close()
        if not events:
            return SupervisorResult(
                route="calendar",
                answer=(
                    "No events in Cluny's local calendar.sqlite. "
                    "Import with `cluny calendar import file.ics`, or — if you use Kosistenz — "
                    "set CLUNY_KOSISTENZ_JOURNAL_DIR and include your schedule in the question."
                ),
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
    context: str | None = None,
    context_json: KosistenzContext | dict | None = None,
    history_prefix: str | None = None,
    collection_name: str | None = None,
) -> SupervisorResult:
    settings = settings or Settings.load()
    merged = format_chat_question(
        question,
        context,
        context_json=context_json,
        history_prefix=history_prefix,
    )
    route = classify_intent(merged, settings)

    if route == "calendar":
        return _calendar_answer(settings, merged, collection_name=collection_name)

    if route == "planner":
        result = run_agent(merged, settings=settings, mode="planner")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    if route == "tasks_agent":
        result = run_agent(merged, settings=settings, mode="tasks")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    if route == "knowledge_agent":
        result = run_agent(merged, settings=settings, mode="knowledge")
        return SupervisorResult(route=route, answer=result.answer, tool_calls=result.tool_calls)

    return _result_from_rag(
        "ask",
        rag_answer(merged, settings=settings, collection_name=collection_name),
    )


def run_chat_stream(
    question: str,
    *,
    settings: Settings | None = None,
    context: str | None = None,
    context_json: KosistenzContext | dict | None = None,
    history_prefix: str | None = None,
    k: int = 5,
    collection_name: str | None = None,
) -> tuple[Route, Iterator[str], tuple[SourceCitation, ...], bool]:
    """
    Stream tokens for ask/calendar RAG routes; non-stream routes yield one chunk.
    Returns (route, token_iterator, sources, empty_index).
    """
    settings = settings or Settings.load()
    merged = format_chat_question(
        question,
        context,
        context_json=context_json,
        history_prefix=history_prefix,
    )
    route = classify_intent(merged, settings)

    if route in ("ask", "calendar") and (route == "ask" or settings.kosistenz_journal_dir):
        stream, sources, empty = rag_answer_stream(
            merged,
            k=k,
            settings=settings,
            collection_name=collection_name,
        )
        cites = tuple(SourceCitation.from_rag(s) for s in sources)
        return route, stream, cites, empty

    result = run_chat(
        question,
        settings=settings,
        context=context,
        context_json=context_json,
        history_prefix=history_prefix,
        collection_name=collection_name,
    )

    def _once() -> Iterator[str]:
        yield result.answer

    return result.route, _once(), result.sources, False
