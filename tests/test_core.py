"""Tests for Cluny core modules (no Ollama required)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cluny.chunking import chunk_text
from cluny.config import Settings
from cluny.documents import IndexResult, add_file, delete_document
from cluny.library_db import (
    connect,
    delete_chunks_for_doc,
    fts_search,
    get_by_path,
    init_schema,
    replace_chunks,
    resolve_document,
    upsert_document,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        ollama_base_url="http://127.0.0.1:11434",
        chat_model="test",
        embed_model="test",
        data_dir=tmp_path / ".cluny",
        catalog_dir_name="library",
        library_sqlite_name="library.sqlite",
        pdf_ocr_mode="never",
        url_mode="open",
        url_allow_hosts=frozenset(),
        url_block_hosts=frozenset(),
        url_max_bytes=1_000_000,
        url_timeout_sec=30.0,
        url_user_agent="test",
        hybrid_vector_weight=0.5,
        retrieval_k=10,
        ollama_timeout_sec=30.0,
        ollama_retries=0,
    )


def test_chunk_text_overlap():
    text = "word " * 500
    chunks = chunk_text(text, max_chars=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_chunk_text_sentence_aware():
    text = "First sentence here. Second sentence follows. Third one too."
    chunks = chunk_text(text, max_chars=80, overlap=10)
    assert chunks
    assert any("." in c for c in chunks)


def test_content_hash_skip(settings: Settings, tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("Hello unchanged content for skip test.", encoding="utf-8")

    mock_collection = MagicMock()
    mock_ollama = MagicMock()
    mock_ollama.embed.return_value = [0.1, 0.2, 0.3]

    result1 = add_file(settings, mock_collection, mock_ollama, f)
    assert result1.unchanged is False
    assert mock_ollama.embed.call_count >= 1
    embed_calls_after_first = mock_ollama.embed.call_count

    result2 = add_file(settings, mock_collection, mock_ollama, f)
    assert result2.unchanged is True
    assert mock_ollama.embed.call_count == embed_calls_after_first


def test_library_delete(settings: Settings, tmp_path: Path):
    f = tmp_path / "del.txt"
    f.write_text("Delete me please.", encoding="utf-8")

    mock_collection = MagicMock()
    mock_ollama = MagicMock()
    mock_ollama.embed.return_value = [0.5, 0.5]

    result = add_file(settings, mock_collection, mock_ollama, f)
    conn = connect(settings)
    assert get_by_path(conn, str(f.resolve())) is not None
    conn.close()

    doc_id = delete_document(settings, mock_collection, result.doc_id)
    assert doc_id == result.doc_id

    conn = connect(settings)
    assert get_by_path(conn, str(f.resolve())) is None
    conn.close()
    mock_collection.delete.assert_called()


def test_fts_search(settings: Settings):
    conn = connect(settings)
    doc_id = "abc123"
    upsert_document(conn, doc_id, "/tmp/x.txt", "txt", "Title", "hash", 10, 2)
    replace_chunks(conn, doc_id, ["working memory limits", "unrelated topic"])
    conn.close()

    conn = connect(settings)
    hits = fts_search(conn, "working memory", limit=5)
    conn.close()
    assert hits
    assert any("working" in t.lower() for _, _, t in hits)


def test_resolve_document_by_prefix(settings: Settings):
    conn = connect(settings)
    upsert_document(
        conn, "deadbeef01", "/path/a.md", "md", "A", "h", 1, 1
    )
    conn.close()

    conn = connect(settings)
    doc = resolve_document(conn, "deadbeef")
    conn.close()
    assert doc is not None
    assert doc.id == "deadbeef01"


def test_delete_chunks_for_doc(settings: Settings):
    conn = connect(settings)
    upsert_document(conn, "d1", "/p", "txt", None, "h", 1, 2)
    replace_chunks(conn, "d1", ["alpha", "beta"])
    delete_chunks_for_doc(conn, "d1")
    cur = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", ("d1",))
    assert cur.fetchone()[0] == 0
    conn.close()
