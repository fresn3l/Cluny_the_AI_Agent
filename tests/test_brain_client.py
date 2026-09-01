"""Tests for brain HTTP client dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cluny.brain_client import chat_brain, ingest_text_brain
from cluny.config import Settings
from cluny.supervisor import SourceCitation, SupervisorResult


def test_chat_brain_in_process(settings):
    with patch("cluny.chat_service.api_chat") as mock_api:
        mock_api.return_value = {
            "route": "ask",
            "answer": "hi",
            "tool_calls": [],
            "sources": [],
            "session_id": "abc",
        }
        result = chat_brain("hello", settings=settings)
    assert result.answer == "hi"
    mock_api.assert_called_once()


def test_chat_brain_http(monkeypatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_BRAIN_URL", "http://127.0.0.1:8787")
    settings = Settings.load()
    with patch("cluny.brain_client.BrainClient.chat") as mock_http:
        mock_http.return_value = (
            SupervisorResult(
                route="ask",
                answer="via http",
                tool_calls=[],
                sources=(SourceCitation(label="n", snippet="s"),),
            ),
            "sess1",
        )
        result = chat_brain("hello", settings=settings)
    assert result.answer == "via http"
    assert len(result.sources) == 1


def test_ingest_text_brain_in_process(settings):
    with (
        patch("cluny.documents.add_inline_text") as mock_add,
        patch("cluny.store.get_collection"),
        patch("cluny.ollama_client.OllamaClient"),
    ):
        mock_add.return_value = MagicMock(chunk_count=3, unchanged=False)
        count, unchanged = ingest_text_brain("note text", settings=settings)
    assert count == 3
    assert unchanged is False
