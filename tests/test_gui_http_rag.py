"""Tests for RagRunnable HTTP streaming in the full GUI."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PySide6")

from cluny.query import RagAnswer


def _rag_runnable():
    from cluny.gui.main_window import RagRunnable

    return RagRunnable


def test_rag_runnable_uses_http_stream(settings, monkeypatch):
    monkeypatch.setenv("CLUNY_BRAIN_URL", "http://127.0.0.1:8787")
    RagRunnable = _rag_runnable()

    events = [
        {"route": "ask", "token": "Hello"},
        {"sources": [{"label": "doc", "snippet": "excerpt", "doc_path": "/x", "chunk_index": 0}]},
        "[DONE]",
    ]

    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter(events)

    tokens: list[str] = []
    finished: list[RagAnswer] = []

    runnable = RagRunnable("question?", k=5, agent_mode="ask")
    runnable.signals.token.connect(tokens.append)
    runnable.signals.finished.connect(finished.append)

    with (
        patch("cluny.gui.main_window.BrainClient.from_settings", return_value=mock_client),
        patch("cluny.gui.main_window.Settings.load", return_value=settings),
    ):
        runnable.run()

    assert tokens == ["Hello"]
    assert len(finished) == 1
    assert finished[0].answer == "Hello"
    assert len(finished[0].sources) == 1
    mock_client.chat_stream.assert_called_once()


def test_rag_runnable_in_process_when_no_brain_url(settings):
    RagRunnable = _rag_runnable()
    runnable = RagRunnable("hi", k=3, agent_mode="ask")
    tokens: list[str] = []
    runnable.signals.token.connect(tokens.append)

    with (
        patch("cluny.gui.main_window.BrainClient.from_settings", return_value=None),
        patch("cluny.gui.main_window.Settings.load", return_value=settings),
        patch(
            "cluny.gui.main_window.rag_answer_stream",
            return_value=(iter(["tok"]), (), False),
        ),
    ):
        runnable.run()

    assert tokens == ["tok"]
