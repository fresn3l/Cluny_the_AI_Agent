"""Tests for collection-scoped retrieval."""

from __future__ import annotations

from cluny.config import Settings
from cluny.library_db import (
    add_doc_to_collection,
    connect,
    create_collection,
    replace_chunks,
    upsert_document,
)
from cluny.query import EMPTY_COLLECTION_MESSAGE, retrieve


def test_retrieve_scoped_to_collection(settings: Settings):
    conn = connect(settings)
    create_collection(conn, "research")
    upsert_document(conn, "d1", "/a.md", "md", "A", "h1", 10, 1)
    upsert_document(conn, "d2", "/b.md", "md", "B", "h2", 10, 1)
    replace_chunks(conn, "d1", ["alpha beta unique"])
    replace_chunks(conn, "d2", ["gamma delta other"])
    add_doc_to_collection(conn, "d1", "research")
    conn.close()

    all_chunks = retrieve("alpha unique", k=5, settings=settings, fts_only=True)
    assert any("alpha" in c.text for c in all_chunks)

    scoped = retrieve(
        "alpha unique",
        k=5,
        settings=settings,
        fts_only=True,
        collection_name="research",
    )
    assert len(scoped) >= 1
    assert all("alpha" in c.text or c.doc_id == "d1" for c in scoped)

    empty = retrieve(
        "alpha unique",
        k=5,
        settings=settings,
        fts_only=True,
        collection_name="nonexistent",
    )
    assert empty == []


def test_empty_collection_message():
    from cluny.query import _empty_rag_message

    assert "collection" in _empty_rag_message("research").lower()
    assert _empty_rag_message(None) != EMPTY_COLLECTION_MESSAGE
