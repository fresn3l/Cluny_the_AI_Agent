"""Tests for widget glance helpers (no Qt)."""

from __future__ import annotations

from cluny.tasks_db import connect as tasks_connect, create_task
from cluny.widget.glance import build_glance_summary, format_glance_text


def test_build_glance_summary_empty(settings):
    summary = build_glance_summary(settings)
    assert summary.doc_count == 0
    assert summary.chunk_count == 0
    assert summary.tasks_due_week == ()
    assert summary.next_event is None


def test_glance_includes_due_tasks(settings):
    conn = tasks_connect(settings)
    create_task(conn, "Soon", due_at="+1d")
    conn.close()
    summary = build_glance_summary(settings)
    assert "Soon" in summary.tasks_due_week


def test_format_glance_text(settings):
    summary = build_glance_summary(settings)
    text = format_glance_text(summary)
    assert "Documents:" in text
    assert "Vector chunks:" in text
