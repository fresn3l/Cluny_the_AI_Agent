"""Tests for Brain tab HTTP endpoints (library, sessions, user config, file ingest)."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.documents import IndexResult


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    return TestClient(create_app())


def test_stats(client: TestClient):
    r = client.get("/stats")
    assert r.status_code == 200
    data = r.json()
    assert "doc_count" in data
    assert "chunk_count" in data
    assert "chat_model" in data


def test_user_config_get_put(client: TestClient):
    r = client.get("/user/config")
    assert r.status_code == 200
    assert "retrieval_k" in r.json()
    r = client.put("/user/config", json={"retrieval_k": 8, "agent_mode": "ask"})
    assert r.status_code == 200
    assert r.json()["retrieval_k"] == 8
    assert r.json()["agent_mode"] == "ask"


def test_library_collections(client: TestClient):
    r = client.get("/library/collections")
    assert r.status_code == 200
    data = r.json()
    assert "collections" in data
    assert "sources" in data


def test_library_list(client: TestClient):
    r = client.get("/library", params={"collection": "journal"})
    assert r.status_code == 200
    assert r.json()["collection"] == "journal"


def test_sessions_create_list_messages(client: TestClient):
    created = client.post("/sessions", json={"title": "Test chat"})
    assert created.status_code == 200
    sid = created.json()["session_id"]
    listed = client.get("/sessions")
    assert listed.status_code == 200
    ids = [row["id"] for row in listed.json()["sessions"]]
    assert sid in ids
    msgs = client.get(f"/sessions/{sid}/messages")
    assert msgs.status_code == 200
    assert msgs.json()["session_id"] == sid


def test_sessions_messages_404(client: TestClient):
    r = client.get("/sessions/missing-id/messages")
    assert r.status_code == 404


def test_ingest_file(client: TestClient):
    with patch("cluny.gui_api.add_file") as mock_add:
        mock_add.return_value = IndexResult(doc_id="doc1", chunk_count=3, unchanged=False)
        r = client.post(
            "/ingest/file",
            files={"file": ("notes.txt", BytesIO(b"hello brain"), "text/plain")},
            data={"title": "Notes", "collection": "journal"},
        )
    assert r.status_code == 200
    assert r.json()["doc_id"] == "doc1"
    assert r.json()["chunk_count"] == 3


def test_library_delete_not_found(client: TestClient):
    r = client.delete("/library/missing-doc")
    assert r.status_code == 404


def test_library_get_patch_and_collections(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from cluny.config import Settings
    from cluny.library_db import (
        add_doc_to_collection,
        connect,
        upsert_document,
    )

    settings = Settings.load()
    conn = connect(settings)
    upsert_document(
        conn,
        "abc123def456",
        "inline:test:hash1",
        "inline",
        "Sample Doc",
        "hash1",
        12,
        2,
    )
    add_doc_to_collection(conn, "abc123def456", "journal")
    conn.close()

    got = client.get("/library/abc123")
    assert got.status_code == 200
    data = got.json()
    assert data["title"] == "Sample Doc"
    assert "journal" in data["collections"]

    patched = client.patch(
        "/library/abc123",
        json={"title": "Renamed", "collections": ["work"], "tags": ["notes"]},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["title"] == "Renamed"
    assert body["collections"] == ["work"]
    assert body["tags"] == ["notes"]

    created = client.post("/library/collections", json={"name": "archive"})
    assert created.status_code == 200
    assert "archive" in created.json()["collections"]

    deleted = client.delete("/library/collections/archive")
    assert deleted.status_code == 200
    assert "archive" not in deleted.json()["collections"]


def test_library_search(client: TestClient):
    from cluny.config import Settings
    from cluny.library_db import connect, upsert_document

    settings = Settings.load()
    conn = connect(settings)
    upsert_document(
        conn,
        "searchdoc1",
        "inline:search:abc",
        "inline",
        "Find Me",
        "abc",
        5,
        1,
    )
    conn.close()

    r = client.get("/library/search", params={"q": "Find"})
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()["documents"]]
    assert "searchdoc1" in ids


def test_health_includes_stats_fields(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "retrieval_k" in data
    assert "agent_mode" in data
