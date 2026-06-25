"""Task management tools for the agent loop."""

from __future__ import annotations

from typing import Any

from cluny.config import Settings
from cluny.dates import parse_due
from cluny.tasks_db import (
    complete_task,
    connect,
    create_task,
    list_tasks,
    resolve_task,
    update_task,
)
from cluny.tools.registry import Tool


def _parse_due(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    return parse_due(str(raw))


def _create_task(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        return {"error": "title is required"}
    conn = connect(settings)
    task = create_task(
        conn,
        title,
        due_at=_parse_due(args.get("due_at")),
        notes=str(args.get("notes", "")).strip() or None,
        project_id=str(args.get("project_id", "")).strip() or None,
        recurrence=str(args.get("recurrence", "")).strip() or None,
    )
    conn.close()
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "due_at": task.due_at,
        "recurrence": task.recurrence,
    }


def _list_tasks(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    conn = connect(settings)
    status = str(args.get("status", "")).strip() or None
    project = str(args.get("project_id", "")).strip() or None
    due_week = bool(args.get("due_week", False))
    rows = list_tasks(conn, status=status, project_id=project, due_week=due_week)
    conn.close()
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_at": t.due_at,
                "notes": t.notes,
                "project_id": t.project_id,
                "recurrence": t.recurrence,
            }
            for t in rows
        ]
    }


def _update_task(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()
    if not task_id:
        return {"error": "task_id is required"}
    conn = connect(settings)
    resolved = resolve_task(conn, task_id)
    if resolved is None:
        conn.close()
        return {"error": f"task not found: {task_id}"}
    updated = update_task(
        conn,
        resolved.id,
        title=args.get("title"),
        due_at=_parse_due(args.get("due_at")) if "due_at" in args else None,
        notes=args.get("notes"),
        status=args.get("status"),
        project_id=args.get("project_id"),
    )
    conn.close()
    if updated is None:
        return {"error": "update failed"}
    return {"id": updated.id, "title": updated.title, "status": updated.status}


def _complete_task(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    task_id = str(args.get("task_id", "")).strip()
    if not task_id:
        return {"error": "task_id is required"}
    conn = connect(settings)
    resolved = resolve_task(conn, task_id)
    if resolved is None:
        conn.close()
        return {"error": f"task not found: {task_id}"}
    done = complete_task(conn, resolved.id)
    conn.close()
    if done is None:
        return {"error": "complete failed"}
    return {"id": done.id, "title": done.title, "status": done.status}


def build_task_tools(settings: Settings) -> list[Tool]:
    return [
        Tool(
            name="create_task",
            description="Create a new task with optional due date and notes.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due_at": {"type": "string", "description": "ISO date or free text"},
                    "notes": {"type": "string"},
                    "project_id": {"type": "string"},
                },
                "required": ["title"],
            },
            handler=lambda args: _create_task(args, settings),
        ),
        Tool(
            name="list_tasks",
            description="List tasks, optionally filtered by status (open or done).",
            parameters={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "done"]},
                    "project_id": {"type": "string"},
                    "due_week": {"type": "boolean", "description": "Only tasks due in next 7 days"},
                },
            },
            handler=lambda args: _list_tasks(args, settings),
        ),
        Tool(
            name="update_task",
            description="Update an existing task by id.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "title": {"type": "string"},
                    "due_at": {"type": "string"},
                    "notes": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["task_id"],
            },
            handler=lambda args: _update_task(args, settings),
        ),
        Tool(
            name="complete_task",
            description="Mark a task as done. Use only when the user explicitly asks.",
            parameters={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
            handler=lambda args: _complete_task(args, settings),
        ),
    ]
