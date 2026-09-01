"""API tests for collection filter and task sync."""

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


def test_search_with_collection(client: TestClient):
    chunk = RetrievedChunk(
        text="research only",
        label="paper.md",
        doc_path="/paper.md",
        chunk_index=0,
        score=0.9,
        doc_id="abc",
    )
    with patch("cluny.api.retrieve", return_value=[chunk]) as mock_retrieve:
        r = client.post("/search", json={"query": "topic", "k": 3, "collection": "research"})
    assert r.status_code == 200
    assert r.json()["collection"] == "research"
    mock_retrieve.assert_called_once()
    assert mock_retrieve.call_args.kwargs["collection_name"] == "research"


def test_tasks_sync_roundtrip(client: TestClient):
    r = client.post(
        "/tasks/sync",
        json={
            "external_id": "kos-100",
            "title": "Mirror todo",
            "due_at": "2026-09-10",
        },
    )
    assert r.status_code == 200
    assert r.json()["external_id"] == "kos-100"

    r2 = client.get("/tasks/sync/kos-100")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Mirror todo"

    r3 = client.get("/tasks/sync")
    assert r3.status_code == 200
    assert len(r3.json()["tasks"]) == 1

    r4 = client.delete("/tasks/sync/kos-100")
    assert r4.status_code == 200
    assert client.get("/tasks/sync/kos-100").status_code == 404
