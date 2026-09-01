"""Kosistenz brain API tests (widget contract)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.kosistenz_context import KosistenzContext
from cluny.proposals import WorkProposal
from cluny.query import RetrievedChunk, RagAnswer, RagSource
from cluny.supervisor import SourceCitation, SupervisorResult


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_SUPERVISOR", "regex")
    return TestClient(create_app())


def test_health_brain_ready(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "brain_ready" in data
    assert "message" in data


def test_chat_with_structured_context_mocked(client: TestClient):
    result = SupervisorResult(
        route="ask",
        answer="Focus on Thursday.",
        tool_calls=[],
        sources=(SourceCitation(label="note.md", snippet="deadline thu"),),
    )
    with patch("cluny.chat_service.run_chat", return_value=result):
        r = client.post(
            "/chat",
            json={
                "question": "What should I prioritize?",
                "context_json": {
                    "date": "2026-09-01",
                    "deadline_todos": [{"title": "Send agenda", "due": "2026-09-04"}],
                },
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Focus on Thursday."
    assert body["session_id"]
    assert body["sources"][0]["label"] == "note.md"


def test_chat_stream_mocked(client: TestClient):
    def fake_stream(*args, **kwargs):
        def gen():
            yield json.dumps({"route": "ask", "session_id": "abc123"})
            yield json.dumps({"sources": [{"label": "j", "snippet": "x"}]})
            yield json.dumps({"token": "Hello"})
            yield "[DONE]"

        return gen()

    with patch("cluny.api.api_chat_stream_events", side_effect=fake_stream):
        r = client.post("/chat/stream", json={"question": "Hi"})
    assert r.status_code == 200
    assert "data:" in r.text
    assert "Hello" in r.text


def test_chat_unknown_session(client: TestClient):
    r = client.post(
        "/chat",
        json={"question": "Hi", "session_id": "not-a-real-session-id"},
    )
    assert r.status_code == 404


def test_propose_structured_context(client: TestClient):
    with patch(
        "cluny.api.run_proposals",
        return_value=[WorkProposal(title="Draft agenda", estimate_minutes=20, due=None, keywords=[])],
    ):
        r = client.post(
            "/propose",
            json={
                "question": "Prep for sync",
                "context_json": {"events_today": [{"title": "Sync", "start": "14:00"}]},
            },
        )
    assert r.status_code == 200
    assert r.json()["proposals"][0]["title"] == "Draft agenda"


def test_ask_accepts_context_and_session(client: TestClient):
    with patch("cluny.api.api_chat_stream_events") as mock_stream:
        mock_stream.return_value = iter(['{"session_id":"s1","route":"ask"}', "[DONE]"])
        r = client.post(
            "/ask",
            json={"question": "Summarize my week", "context": "Goal: ship", "session_id": None},
        )
    assert r.status_code == 200
