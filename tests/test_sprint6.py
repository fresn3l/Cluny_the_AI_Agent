"""Tests for Sprint 6 features."""

from __future__ import annotations

from pathlib import Path

import pytest

from cluny.calendar_db import import_ics, connect as cal_connect, list_upcoming
from cluny.config import Settings
from cluny.library_db import (
    add_doc_to_collection,
    connect,
    create_collection,
    doc_ids_in_collection,
    duplicate_hash_groups,
    upsert_document,
)
from cluny.supervisor import classify_intent


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
        embed_batch_size=8,
        rerank_mode="off",
        chunk_pdf_size=1500,
        chunk_pdf_overlap=250,
        chunk_md_size=1200,
        chunk_md_overlap=200,
        chunk_journal_size=800,
        chunk_journal_overlap=100,
        chunk_default_size=1200,
        chunk_default_overlap=200,
    )


def test_collections(settings: Settings):
    conn = connect(settings)
    create_collection(conn, "research")
    upsert_document(conn, "d1", "/a.md", "md", "A", "h1", 1, 1)
    add_doc_to_collection(conn, "d1", "research")
    ids = doc_ids_in_collection(conn, "research")
    conn.close()
    assert "d1" in ids


def test_duplicate_hash_report(settings: Settings):
    conn = connect(settings)
    upsert_document(conn, "d1", "/a.md", "md", "A", "same", 1, 1)
    upsert_document(conn, "d2", "/b.md", "md", "B", "same", 1, 1)
    groups = duplicate_hash_groups(conn)
    conn.close()
    assert "same" in groups
    assert len(groups["same"]) == 2


def test_supervisor_routing():
    assert classify_intent("What's due this week?") == "tasks_agent"
    assert classify_intent("What did Smith say in my notes?") == "knowledge_agent"
    assert classify_intent("What's on my calendar tomorrow?") == "calendar"


def test_ics_import(settings: Settings, tmp_path: Path):
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team sync\nDTSTART:20260625T100000Z\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    n = import_ics(ics, settings)
    assert n == 1
    conn = cal_connect(settings)
    events = list_upcoming(conn)
    conn.close()
    assert events[0].summary == "Team sync"
