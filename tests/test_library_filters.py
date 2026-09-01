"""Tests for library source/collection filters."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.library_db import (
    add_doc_to_collection,
    connect,
    inline_source_from_path,
    list_documents,
    list_inline_sources,
    upsert_document,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    return TestClient(create_app())


def test_inline_source_from_path():
    assert inline_source_from_path("inline:kosistenz-journal:abc123") == "kosistenz-journal"
    assert inline_source_from_path("/Users/me/notes.pdf") is None


def test_list_documents_by_source_and_collection(settings):
    conn = connect(settings)
    upsert_document(
        conn,
        "doc-journal",
        "inline:kosistenz-journal:aaa",
        "journal",
        "2026-09-01",
        "hash1",
        100,
        2,
    )
    upsert_document(
        conn,
        "doc-analytics",
        "inline:kosistenz-analytics:bbb",
        "inline",
        "analytics-2026-W35",
        "hash2",
        80,
        1,
    )
    add_doc_to_collection(conn, "doc-journal", "journal")
    add_doc_to_collection(conn, "doc-analytics", "analytics")

    journal_only = list_documents(conn, source="kosistenz-journal")
    assert [d.id for d in journal_only] == ["doc-journal"]

    analytics_coll = list_documents(conn, collection="analytics")
    assert [d.id for d in analytics_coll] == ["doc-analytics"]

    both = list_documents(conn, collection="journal", source="kosistenz-journal")
    assert [d.id for d in both] == ["doc-journal"]

    sources = list_inline_sources(conn)
    assert sources == ["kosistenz-analytics", "kosistenz-journal"]
    conn.close()


def test_library_api_filters(settings, client: TestClient):
    conn = connect(settings)
    upsert_document(
        conn,
        "doc-journal",
        "inline:kosistenz-journal:aaa",
        "journal",
        "2026-09-01",
        "hash1",
        100,
        2,
    )
    add_doc_to_collection(conn, "doc-journal", "journal")
    conn.close()

    r = client.get("/library", params={"source": "kosistenz-journal"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["documents"]) == 1
    assert data["documents"][0]["source"] == "kosistenz-journal"
    assert data["documents"][0]["collections"] == ["journal"]
