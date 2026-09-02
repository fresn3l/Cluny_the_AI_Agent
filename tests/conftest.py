"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from cluny.config import Settings


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
        supervisor_mode="regex",
        api_bind_host="127.0.0.1",
        api_port=8787,
        api_token="",
        backup_dir=tmp_path / "backups",
        kosistenz_journal_dir=None,
        brain_url="",
        capture_source="telegram-capture",
        capture_collection="capture",
        telegram_bot_token="",
        telegram_allowed_user_ids=frozenset({12345}),
    )
