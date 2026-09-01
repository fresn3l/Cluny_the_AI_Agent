"""Tests for Kosistenz task mirror via external_id."""

from __future__ import annotations

from cluny.task_sync import api_delete_synced_task, api_get_synced_task, api_list_synced_tasks, api_sync_task
from cluny.tasks_db import connect, find_task_by_external_id


def test_sync_task_upsert_and_list(settings):
    api_sync_task(
        settings=settings,
        external_id="kos-42",
        title="Send agenda",
        due_at="2026-09-04",
    )
    task = api_get_synced_task(settings, "kos-42")
    assert task is not None
    assert task["title"] == "Send agenda"
    assert task["external_id"] == "kos-42"

    api_sync_task(
        settings=settings,
        external_id="kos-42",
        title="Send agenda (updated)",
        status="done",
    )
    updated = api_get_synced_task(settings, "kos-42")
    assert updated is not None
    assert updated["title"] == "Send agenda (updated)"
    assert updated["status"] == "done"

    listed = api_list_synced_tasks(settings)
    assert any(t["external_id"] == "kos-42" for t in listed)

    assert api_delete_synced_task(settings, "kos-42")
    assert api_get_synced_task(settings, "kos-42") is None


def test_sync_task_unique_external_id(settings):
    api_sync_task(settings=settings, external_id="kos-1", title="One")
    conn = connect(settings)
    assert find_task_by_external_id(conn, "kos-1") is not None
    conn.close()
