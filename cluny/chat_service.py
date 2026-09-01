"""Chat orchestration for Kosistenz widget and HTTP API."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from cluny.config import Settings
from cluny.kosistenz_context import KosistenzContext
from cluny.sessions import (
    add_message,
    connect as sessions_connect,
    create_session,
    get_session,
    list_messages,
    session_history_prefix,
)
from cluny.supervisor import SupervisorResult, run_chat, run_chat_stream


class SessionNotFoundError(ValueError):
    pass


def resolve_session_id(
    settings: Settings,
    session_id: str | None,
    *,
    title_hint: str | None = None,
) -> str:
    conn = sessions_connect(settings)
    if session_id:
        if get_session(conn, session_id) is None:
            conn.close()
            raise SessionNotFoundError(f"Session not found: {session_id}")
    else:
        session_id = create_session(conn, (title_hint or "Kosistenz chat")[:120])
    conn.close()
    return session_id


def history_prefix_for_session(settings: Settings, session_id: str) -> str:
    conn = sessions_connect(settings)
    messages = list_messages(conn, session_id)
    conn.close()
    return session_history_prefix(messages)


def persist_turn(settings: Settings, session_id: str, question: str, answer: str) -> None:
    conn = sessions_connect(settings)
    add_message(conn, session_id, "user", question)
    add_message(conn, session_id, "assistant", answer)
    conn.close()


def chat_result_to_dict(result: SupervisorResult, *, session_id: str) -> dict[str, Any]:
    return {
        "route": result.route,
        "answer": result.answer,
        "tool_calls": result.tool_calls,
        "sources": [s.to_dict() for s in result.sources],
        "session_id": session_id,
    }


def api_chat(
    question: str,
    *,
    settings: Settings,
    context: str | None = None,
    context_json: KosistenzContext | dict | None = None,
    session_id: str | None = None,
    collection: str | None = None,
) -> dict[str, Any]:
    sid = resolve_session_id(settings, session_id, title_hint=question)
    prefix = history_prefix_for_session(settings, sid)
    result = run_chat(
        question,
        settings=settings,
        context=context,
        context_json=context_json,
        history_prefix=prefix or None,
        collection_name=collection,
    )
    persist_turn(settings, sid, question, result.answer)
    return chat_result_to_dict(result, session_id=sid)


def api_chat_stream_events(
    question: str,
    *,
    settings: Settings,
    context: str | None = None,
    context_json: KosistenzContext | dict | None = None,
    session_id: str | None = None,
    k: int = 5,
    collection: str | None = None,
) -> Iterator[str]:
    """Yield JSON payload strings for SSE (caller adds data: prefix)."""
    sid = resolve_session_id(settings, session_id, title_hint=question)
    prefix = history_prefix_for_session(settings, sid)
    route, stream, sources, _empty = run_chat_stream(
        question,
        settings=settings,
        context=context,
        context_json=context_json,
        history_prefix=prefix or None,
        k=k,
        collection_name=collection,
    )

    collected: list[str] = []

    def gen() -> Iterator[str]:
        yield json.dumps({"route": route, "session_id": sid})
        if sources:
            yield json.dumps({"sources": [s.to_dict() for s in sources]})
        for token in stream:
            collected.append(token)
            yield json.dumps({"token": token})
        persist_turn(settings, sid, question, "".join(collected))
        yield "[DONE]"

    return gen()
