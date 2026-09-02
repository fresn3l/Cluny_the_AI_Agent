"""Chat session persistence for GUI and CLI."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cluny.config import Settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path(settings: Settings) -> Path:
    p = settings.data_dir / "sessions.sqlite"
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
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class MessageRow:
    role: str
    content: str
    created_at: str


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    cur = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return str(row[0]) if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def create_session(conn: sqlite3.Connection, title: str | None = None) -> str:
    sid = uuid.uuid4().hex
    now = _utc_now()
    conn.execute(
        "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (sid, title, now, now),
    )
    conn.commit()
    return sid


def get_or_create_last_session(conn: sqlite3.Connection) -> str:
    last = get_state(conn, "last_session_id")
    if last:
        cur = conn.execute("SELECT id FROM sessions WHERE id = ?", (last,))
        if cur.fetchone():
            return last
    sid = create_session(conn, "Default")
    set_state(conn, "last_session_id", sid)
    return sid


def add_message(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> None:
    now = _utc_now()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()


def list_messages(conn: sqlite3.Connection, session_id: str) -> list[MessageRow]:
    cur = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    )
    return [MessageRow(str(r[0]), str(r[1]), str(r[2])) for r in cur.fetchall()]


def get_session(conn: sqlite3.Connection, session_id: str) -> str | None:
    cur = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    return str(row[0]) if row else None


@dataclass(frozen=True)
class SessionRow:
    id: str
    title: str | None
    created_at: str
    updated_at: str


def list_sessions(conn: sqlite3.Connection, *, limit: int = 50) -> list[SessionRow]:
    cur = conn.execute(
        """
        SELECT id, title, created_at, updated_at FROM sessions
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (max(1, limit),),
    )
    return [
        SessionRow(
            id=str(r[0]),
            title=str(r[1]) if r[1] is not None else None,
            created_at=str(r[2]),
            updated_at=str(r[3]),
        )
        for r in cur.fetchall()
    ]


def session_history_prefix(messages: list[MessageRow], *, max_turns: int = 6) -> str:
    """Format recent turns for inclusion in the chat prompt."""
    recent = messages[-max_turns:]
    if not recent:
        return ""
    lines = [f"{m.role}: {m.content}" for m in recent]
    return "Previous conversation:\n" + "\n".join(lines) + "\n\n"
