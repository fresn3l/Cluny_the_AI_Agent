"""Optional Kosistenz task mirror via external_id (Cluny does not own schedule)."""

from __future__ import annotations

from typing import Any

from cluny.config import Settings
from cluny.tasks_db import (
    TaskRow,
    connect,
    delete_task_by_external_id,
    find_task_by_external_id,
    list_synced_tasks,
    sync_task_by_external_id,
)


def task_to_dict(task: TaskRow) -> dict[str, Any]:
    return {
        "id": task.id,
        "external_id": task.external_id,
        "title": task.title,
        "status": task.status,
        "due_at": task.due_at,
        "notes": task.notes,
        "project_id": task.project_id,
        "recurrence": task.recurrence,
        "created_at": task.created_at,
    }


def api_sync_task(
    *,
    settings: Settings,
    external_id: str,
    title: str,
    status: str = "open",
    due_at: str | None = None,
    notes: str | None = None,
    project_id: str | None = None,
    recurrence: str | None = None,
) -> dict[str, Any]:
    conn = connect(settings)
    task = sync_task_by_external_id(
        conn,
        external_id,
        title,
        status=status,
        due_at=due_at,
        notes=notes,
        project_id=project_id,
        recurrence=recurrence,
    )
    conn.close()
    return task_to_dict(task)


def api_get_synced_task(settings: Settings, external_id: str) -> dict[str, Any] | None:
    conn = connect(settings)
    task = find_task_by_external_id(conn, external_id)
    conn.close()
    return task_to_dict(task) if task else None


def api_list_synced_tasks(settings: Settings) -> list[dict[str, Any]]:
    conn = connect(settings)
    rows = list_synced_tasks(conn)
    conn.close()
    return [task_to_dict(t) for t in rows]


def api_delete_synced_task(settings: Settings, external_id: str) -> bool:
    conn = connect(settings)
    deleted = delete_task_by_external_id(conn, external_id)
    conn.close()
    return deleted
