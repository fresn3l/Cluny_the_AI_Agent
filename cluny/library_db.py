"""SQLite catalog for documents indexed into Cluny (paths, hashes, chunk counts)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cluny.config import Settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path(settings: Settings) -> Path:
    p = settings.data_dir / "library" / "library.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(settings)))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            title TEXT,
            content_hash TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            ingested_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class DocumentRow:
    id: str
    path: str
    kind: str
    title: str | None
    content_hash: str
    size_bytes: int
    chunk_count: int
    ingested_at: str


def get_by_path(conn: sqlite3.Connection, resolved_path: str) -> DocumentRow | None:
    cur = conn.execute("SELECT * FROM documents WHERE path = ?", (resolved_path,))
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_doc(row)


def _row_to_doc(row: sqlite3.Row) -> DocumentRow:
    return DocumentRow(
        id=str(row["id"]),
        path=str(row["path"]),
        kind=str(row["kind"]),
        title=str(row["title"]) if row["title"] is not None else None,
        content_hash=str(row["content_hash"]),
        size_bytes=int(row["size_bytes"]),
        chunk_count=int(row["chunk_count"]),
        ingested_at=str(row["ingested_at"]),
    )


def upsert_document(
    conn: sqlite3.Connection,
    doc_id: str,
    resolved_path: str,
    kind: str,
    title: str | None,
    content_hash: str,
    size_bytes: int,
    chunk_count: int,
) -> None:
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO documents (id, path, kind, title, content_hash, size_bytes, chunk_count, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            kind = excluded.kind,
            title = excluded.title,
            content_hash = excluded.content_hash,
            size_bytes = excluded.size_bytes,
            chunk_count = excluded.chunk_count,
            ingested_at = excluded.ingested_at
        """,
        (doc_id, resolved_path, kind, title, content_hash, size_bytes, chunk_count, now),
    )
    conn.commit()


def list_documents(conn: sqlite3.Connection) -> list[DocumentRow]:
    cur = conn.execute("SELECT * FROM documents ORDER BY ingested_at DESC")
    return [_row_to_doc(r) for r in cur.fetchall()]


def document_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM documents")
    return int(cur.fetchone()[0])
