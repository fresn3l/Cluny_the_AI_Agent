"""Tests for chat service sessions and API helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cluny.chat_service import SessionNotFoundError, api_chat, resolve_session_id
from cluny.supervisor import SourceCitation, SupervisorResult


def test_resolve_session_creates_new(settings):
    sid = resolve_session_id(settings, None, title_hint="Hello")
    assert len(sid) == 32


def test_resolve_session_not_found(settings):
    with pytest.raises(SessionNotFoundError):
        resolve_session_id(settings, "does-not-exist")


def test_api_chat_persists_and_returns_session(settings):
    result = SupervisorResult(
        route="ask",
        answer="Try the agenda first.",
        tool_calls=[],
        sources=(SourceCitation(label="journal", snippet="meeting notes"),),
    )
    with patch("cluny.chat_service.run_chat", return_value=result):
        data = api_chat("What first?", settings=settings)
    assert data["answer"] == "Try the agenda first."
    assert data["session_id"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["label"] == "journal"

    sid = data["session_id"]
    with patch("cluny.chat_service.run_chat", return_value=result):
        data2 = api_chat("Follow up", settings=settings, session_id=sid)
    assert data2["session_id"] == sid
