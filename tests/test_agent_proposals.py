"""Planner/agent tools: propose, not live task CRUD."""

from __future__ import annotations

from cluny.agent import _build_registry, _tool_allowed, run_agent
from cluny.tasks_db import connect as tasks_connect
from cluny.tools.proposals import clear_agent_proposals


def test_planner_registry_has_create_proposal_not_create_task(settings):
    registry = _build_registry(settings, "planner")
    names = set(registry._tools)  # noqa: SLF001
    assert "create_proposal" in names
    assert "search_brain" in names
    assert "week_from_snapshot" in names
    assert "create_task" not in names
    assert "complete_task" not in names
    assert "update_task" not in names


def test_planner_disallows_live_task_crud():
    assert _tool_allowed("planner", "create_proposal")
    assert _tool_allowed("planner", "search_brain")
    assert not _tool_allowed("planner", "create_task")
    assert not _tool_allowed("planner", "complete_task")
    assert not _tool_allowed("all", "create_task")
    assert _tool_allowed("tasks", "create_task")  # standalone scratch only


def test_planner_execute_create_proposal_leaves_tasks_sqlite(settings):
    clear_agent_proposals()
    conn = tasks_connect(settings)
    before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()

    registry = _build_registry(settings, "planner")
    raw = registry.execute(
        "create_proposal",
        {"title": "Planner proposal", "due": "2026-09-12", "keywords": ["test"]},
    )
    assert "Planner proposal" in raw
    assert "NOT a live" in raw or "proposal" in raw.lower()

    conn = tasks_connect(settings)
    after = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    assert after == before
