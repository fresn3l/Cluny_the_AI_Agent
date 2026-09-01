"""Kosistenz brain API tests (not legacy task/calendar routes)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.query import RetrievedChunk
from cluny.supervisor import SupervisorResult


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_SUPERVISOR", "regex")
    return TestClient(create_app())


def test_health_brain_contract(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["integration"] == "brain-only"
    assert "ollama_ok" in data
    assert "task_count_note" in data


def test_search_mocked(client: TestClient):
    chunk = RetrievedChunk(
        text="week clock packing",
        label="note.md",
        doc_path="/tmp/note.md",
        chunk_index=0,
        score=0.9,
        doc_id="abc",
    )
    with patch("cluny.api.retrieve", return_value=[chunk]):
        r = client.post("/search", json={"query": "packing", "k": 3})
    assert r.status_code == 200
    assert "week clock" in r.json()["chunks"][0]["text"]


def test_chat_mocked(client: TestClient):
    result = SupervisorResult(route="ask", answer="Focus on Thursday deadline.", tool_calls=[])
    with patch("cluny.api.run_chat", return_value=result):
        r = client.post(
            "/chat",
            json={"question": "What should I prioritize? Open: send agenda (Thu)."},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Focus on Thursday deadline."
    assert body["route"] == "ask"


def test_ingest_journal_copy_mocked(client: TestClient):
    mock_result = MagicMock(doc_id="doc-1", chunk_count=2)
    with (
        patch("cluny.api.get_collection"),
        patch("cluny.api.OllamaClient"),
        patch("cluny.api.add_inline_text", return_value=mock_result),
    ):
        r = client.post(
            "/ingest/text",
            json={
                "text": "Journal entry body",
                "catalog": True,
                "source": "kosistenz-journal",
                "title": "2026-09-01 journal",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data["catalog"] is True
    assert data["doc_id"] == "doc-1"


def test_propose_mocked(client: TestClient):
    from cluny.proposals import WorkProposal

    with patch(
        "cluny.api.run_proposals",
        return_value=[WorkProposal(title="Ship feature", estimate_minutes=60, due=None, keywords=["dev"])],
    ):
        r = client.post(
            "/propose",
            json={"question": "What should I work on?", "context": "Goal: ship v1"},
        )
    assert r.status_code == 200
    props = r.json()["proposals"]
    assert props[0]["title"] == "Ship feature"

