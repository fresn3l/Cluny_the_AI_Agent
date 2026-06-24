"""SQLite task store (separate from the knowledge catalog)."""

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
    p = settings.data_dir / "tasks.sqlite"
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
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            due_at TEXT,
            created_at TEXT NOT NULL,
            notes TEXT,
            project_id TEXT
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class TaskRow:
    id: str
    title: str
    status: str
    due_at: str | None
    created_at: str
    notes: str | None
    project_id: str | None


def _row_to_task(row: sqlite3.Row) -> TaskRow:
    return TaskRow(
        id=str(row["id"]),
        title=str(row["title"]),
        status=str(row["status"]),
        due_at=str(row["due_at"]) if row["due_at"] is not None else None,
        created_at=str(row["created_at"]),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        project_id=str(row["project_id"]) if row["project_id"] is not None else None,
    )


def create_task(
    conn: sqlite3.Connection,
    title: str,
    *,
    due_at: str | None = None,
    notes: str | None = None,
    project_id: str | None = None,
) -> TaskRow:
    task_id = uuid.uuid4().hex
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO tasks (id, title, status, due_at, created_at, notes, project_id)
        VALUES (?, ?, 'open', ?, ?, ?, ?)
        """,
        (task_id, title.strip(), due_at, now, notes, project_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    assert row is not None
    return _row_to_task(row)


def list_tasks(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    project_id: str | None = None,
) -> list[TaskRow]:
    q = "SELECT * FROM tasks WHERE 1=1"
    params: list[str] = []
    if status:
        q += " AND status = ?"
        params.append(status)
    if project_id:
        q += " AND project_id = ?"
        params.append(project_id)
    q += " ORDER BY COALESCE(due_at, created_at) ASC"
    cur = conn.execute(q, params)
    return [_row_to_task(r) for r in cur.fetchall()]


def get_task(conn: sqlite3.Connection, task_id: str) -> TaskRow | None:
    cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    return _row_to_task(row) if row else None


def find_task_by_prefix(conn: sqlite3.Connection, prefix: str) -> TaskRow | None:
    cur = conn.execute("SELECT * FROM tasks WHERE id LIKE ?", (f"{prefix}%",))
    rows = cur.fetchall()
    if len(rows) == 1:
        return _row_to_task(rows[0])
    return None


def resolve_task(conn: sqlite3.Connection, identifier: str) -> TaskRow | None:
    t = get_task(conn, identifier)
    if t:
        return t
    return find_task_by_prefix(conn, identifier)


def update_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    title: str | None = None,
    due_at: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
) -> TaskRow | None:
    task = get_task(conn, task_id)
    if task is None:
        return None
    new_title = title.strip() if title is not None else task.title
    new_due = due_at if due_at is not None else task.due_at
    new_notes = notes if notes is not None else task.notes
    new_status = status if status is not None else task.status
    new_project = project_id if project_id is not None else task.project_id
    conn.execute(
        """
        UPDATE tasks SET title=?, due_at=?, notes=?, status=?, project_id=?
        WHERE id=?
        """,
        (new_title, new_due, new_notes, new_status, new_project, task_id),
    )
    conn.commit()
    return get_task(conn, task_id)


def complete_task(conn: sqlite3.Connection, task_id: str) -> TaskRow | None:
    return update_task(conn, task_id, status="done")


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return cur.rowcount > 0
