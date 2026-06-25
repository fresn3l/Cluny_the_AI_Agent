"""Tests for task CRUD (no Ollama)."""

from __future__ import annotations

from pathlib import Path

from cluny.config import Settings
from cluny.dates import parse_due
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


def test_create_and_list_tasks(settings: Settings):
    conn = connect(settings)
    create_task(conn, "Buy milk", due_at="tomorrow")
    rows = list_tasks(conn)
    conn.close()
    assert len(rows) == 1
    assert rows[0].title == "Buy milk"
    assert rows[0].status == "open"
    assert rows[0].due_at is not None
    assert "T" in rows[0].due_at


def test_parse_due_tomorrow():
    iso = parse_due("tomorrow")
    assert iso is not None
    assert iso.endswith("Z")


def test_list_tasks_due_week(settings: Settings):
    conn = connect(settings)
    create_task(conn, "Soon", due_at="+1d")
    create_task(conn, "Later", due_at="+30d")
    week = list_tasks(conn, due_week=True)
    conn.close()
    assert len(week) == 1
    assert week[0].title == "Soon"


def test_task_recurrence(settings: Settings):
    conn = connect(settings)
    t = create_task(conn, "Standup", recurrence="weekly")
    conn.close()
    assert t.recurrence == "weekly"


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
