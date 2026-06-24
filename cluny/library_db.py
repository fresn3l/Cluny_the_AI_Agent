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
    p = settings.catalog_root / settings.library_sqlite_name
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (doc_id, chunk_index),
            FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            doc_id UNINDEXED,
            chunk_index UNINDEXED,
            tokenize='porter unicode61'
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_tags (
            doc_id TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (doc_id, tag_id),
            FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
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


def get_by_id(conn: sqlite3.Connection, doc_id: str) -> DocumentRow | None:
    cur = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return _row_to_doc(row)


def find_by_id_prefix(conn: sqlite3.Connection, prefix: str) -> DocumentRow | None:
    """Return the single document whose id starts with prefix, or None / ambiguous."""
    cur = conn.execute(
        "SELECT * FROM documents WHERE id LIKE ?",
        (f"{prefix}%",),
    )
    rows = cur.fetchall()
    if len(rows) == 1:
        return _row_to_doc(rows[0])
    if len(rows) > 1 and len(prefix) >= 8:
        exact = [r for r in rows if str(r["id"]) == prefix]
        if len(exact) == 1:
            return _row_to_doc(exact[0])
    return None


def resolve_document(
    conn: sqlite3.Connection,
    identifier: str,
) -> DocumentRow | None:
    """Look up by full id, id prefix, or catalog path."""
    doc = get_by_id(conn, identifier)
    if doc is not None:
        return doc
    doc = find_by_id_prefix(conn, identifier)
    if doc is not None:
        return doc
    return get_by_path(conn, identifier)


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


def delete_document_row(conn: sqlite3.Connection, doc_id: str) -> bool:
    cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    return cur.rowcount > 0


def delete_chunks_for_doc(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM chunks_fts WHERE doc_id = ?", (doc_id,))
    conn.commit()


def replace_chunks(
    conn: sqlite3.Connection,
    doc_id: str,
    chunk_texts: list[str],
) -> None:
    """Store chunk text in SQLite and FTS index (used during ingest)."""
    delete_chunks_for_doc(conn, doc_id)
    for i, text in enumerate(chunk_texts):
        conn.execute(
            "INSERT INTO chunks (doc_id, chunk_index, text) VALUES (?, ?, ?)",
            (doc_id, i, text),
        )
        conn.execute(
            "INSERT INTO chunks_fts (text, doc_id, chunk_index) VALUES (?, ?, ?)",
            (text, doc_id, i),
        )
    conn.commit()


def fts_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 10,
) -> list[tuple[str, int, str]]:
    """Return (doc_id, chunk_index, text) rows ranked by FTS5."""
    q = query.strip()
    if not q:
        return []
    # Quote tokens for FTS5 phrase-style matching
    fts_q = " ".join(f'"{tok}"' for tok in q.split() if tok)
    if not fts_q:
        return []
    cur = conn.execute(
        """
        SELECT doc_id, chunk_index, text
        FROM chunks_fts
        WHERE chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_q, limit),
    )
    return [(str(r[0]), int(r[1]), str(r[2])) for r in cur.fetchall()]


def list_documents(
    conn: sqlite3.Connection,
    *,
    tag: str | None = None,
) -> list[DocumentRow]:
    if tag:
        cur = conn.execute(
            """
            SELECT d.* FROM documents d
            JOIN document_tags dt ON d.id = dt.doc_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE t.name = ? COLLATE NOCASE
            ORDER BY d.ingested_at DESC
            """,
            (tag.strip(),),
        )
    else:
        cur = conn.execute("SELECT * FROM documents ORDER BY ingested_at DESC")
    return [_row_to_doc(r) for r in cur.fetchall()]


def document_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM documents")
    return int(cur.fetchone()[0])


def list_tags(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute("SELECT name FROM tags ORDER BY name COLLATE NOCASE")
    return [str(r[0]) for r in cur.fetchall()]


def get_tags_for_doc(conn: sqlite3.Connection, doc_id: str) -> list[str]:
    cur = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN document_tags dt ON t.id = dt.tag_id
        WHERE dt.doc_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (doc_id,),
    )
    return [str(r[0]) for r in cur.fetchall()]


def add_tag_to_doc(conn: sqlite3.Connection, doc_id: str, tag_name: str) -> None:
    name = tag_name.strip()
    if not name:
        raise ValueError("Tag name cannot be empty.")
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
    cur = conn.execute("SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Could not create tag: {tag_name!r}")
    tag_id = int(row[0])
    conn.execute(
        "INSERT OR IGNORE INTO document_tags (doc_id, tag_id) VALUES (?, ?)",
        (doc_id, tag_id),
    )
    conn.commit()


def get_chunk_with_meta(
    conn: sqlite3.Connection,
    doc_id: str,
    chunk_index: int,
) -> tuple[str, str | None, str] | None:
    """Return (doc_path, title, chunk_text) or None."""
    cur = conn.execute(
        """
        SELECT c.text, d.path, d.title
        FROM chunks c
        JOIN documents d ON c.doc_id = d.id
        WHERE c.doc_id = ? AND c.chunk_index = ?
        """,
        (doc_id, chunk_index),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return str(row[1]), (str(row[2]) if row[2] is not None else None), str(row[0])
