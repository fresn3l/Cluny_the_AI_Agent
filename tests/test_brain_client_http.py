"""Tests for BrainClient HTTP helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from cluny.brain_client import BrainClient
from cluny.kosistenz_context import KosistenzContext


def test_brain_client_chat_parses_sources():
    client = BrainClient(base_url="http://127.0.0.1:8787")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "route": "ask",
        "answer": "Done",
        "tool_calls": [],
        "sources": [{"label": "j", "snippet": "x", "doc_path": "/a", "chunk_index": 0}],
        "session_id": "s1",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.post.return_value = mock_resp
        result, sid = client.chat("q", context_json=KosistenzContext(date="2026-09-01"))
    assert sid == "s1"
    assert result.sources[0].label == "j"


def test_brain_client_chat_stream_parses_sse():
    client = BrainClient(base_url="http://127.0.0.1:8787")

    def fake_iter_lines():
        yield f'data: {json.dumps({"route": "ask", "session_id": "s1"})}'
        yield f'data: {json.dumps({"token": "Hi"})}'
        yield "data: [DONE]"

    mock_stream = MagicMock()
    mock_stream.iter_lines.return_value = fake_iter_lines()
    mock_stream.raise_for_status = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_stream
    with patch("httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.stream.return_value = mock_ctx
        events = list(client.chat_stream("q"))
    assert events[0]["session_id"] == "s1"
    assert events[1]["token"] == "Hi"
    assert events[-1] == "[DONE]"
