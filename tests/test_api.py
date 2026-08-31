"""HTTP API tests (no running Ollama)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.query import RetrievedChunk


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_SUPERVISOR", "regex")
    return TestClient(create_app())


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "ollama_ok" in data
    assert "doc_count" in data
    assert "task_count" in data


def test_search_mocked(client: TestClient):
    chunk = RetrievedChunk(
        text="working memory limits",
        label="note.md",
        doc_path="/tmp/note.md",
        chunk_index=0,
        score=0.9,
        doc_id="abc",
    )
    with patch("cluny.api.retrieve", return_value=[chunk]):
        r = client.post("/search", json={"query": "memory", "k": 3})
    assert r.status_code == 200
    data = r.json()
    assert len(data["chunks"]) == 1
    assert "working memory" in data["chunks"][0]["text"]


def test_auth_rejects_bad_token(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_API_TOKEN", "secret")
    client = TestClient(create_app())
    r = client.post("/search", json={"query": "x", "k": 1})
    assert r.status_code == 401
