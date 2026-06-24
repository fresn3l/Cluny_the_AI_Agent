"""Tests for task CRUD (no Ollama)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cluny.config import Settings
from cluny.tasks_db import (
    complete_task,
    connect,
    create_task,
    delete_task,
    list_tasks,
    resolve_task,
    update_task,
)
from cluny.tools.registry import ToolRegistry
from cluny.tools.tasks import build_task_tools


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


def test_create_and_list_tasks(settings: Settings):
    conn = connect(settings)
    create_task(conn, "Buy milk", due_at="tomorrow")
    rows = list_tasks(conn)
    conn.close()
    assert len(rows) == 1
    assert rows[0].title == "Buy milk"
    assert rows[0].status == "open"


def test_complete_task(settings: Settings):
    conn = connect(settings)
    t = create_task(conn, "Finish report")
    done = complete_task(conn, t.id)
    conn.close()
    assert done is not None
    assert done.status == "done"


def test_update_and_delete(settings: Settings):
    conn = connect(settings)
    t = create_task(conn, "Old title")
    update_task(conn, t.id, title="New title", notes="details")
    resolved = resolve_task(conn, t.id[:8])
    assert resolved is not None
    assert resolved.title == "New title"
    assert delete_task(conn, t.id)
    conn.close()


def test_create_task_tool(settings: Settings):
    registry = ToolRegistry(build_task_tools(settings))
    raw = registry.execute("create_task", {"title": "Call dentist", "due_at": "Friday"})
    assert "Call dentist" in raw
    raw2 = registry.execute("list_tasks", {"status": "open"})
    assert "Call dentist" in raw2
