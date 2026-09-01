"""Compact menu-bar widget data helpers (no Qt)."""

from __future__ import annotations

from dataclasses import dataclass

from cluny.config import Settings
from cluny.library_db import connect, document_count
from cluny.store import get_collection
from cluny.tasks_db import connect as tasks_connect, list_tasks


@dataclass(frozen=True)
class GlanceSummary:
    doc_count: int
    chunk_count: int
    tasks_due_week: tuple[str, ...]
    next_event: str | None


def build_glance_summary(settings: Settings) -> GlanceSummary:
    """Load read-only stats for the widget Glance tab (no LLM)."""
    chunk_count = 0
    try:
        chunk_count = get_collection(settings).count()
    except Exception:  # noqa: BLE001
        pass

    conn = connect(settings)
    doc_count = document_count(conn)
    conn.close()

    tasks_conn = tasks_connect(settings)
    due_soon = list_tasks(tasks_conn, status="open", due_week=True)
    tasks_conn.close()
    task_titles = tuple(t.title for t in due_soon[:5])

    next_event: str | None = None
    try:
        from cluny.calendar_db import connect as cal_connect, list_upcoming

        cal_conn = cal_connect(settings)
        events = list_upcoming(cal_conn, limit=1)
        cal_conn.close()
        if events:
            e = events[0]
            next_event = f"{e.summary} ({e.start_at or '?'})"
    except Exception:  # noqa: BLE001
        pass

    return GlanceSummary(
        doc_count=doc_count,
        chunk_count=chunk_count,
        tasks_due_week=task_titles,
        next_event=next_event,
    )


def format_glance_text(summary: GlanceSummary) -> str:
    lines = [
        f"Documents: {summary.doc_count}",
        f"Vector chunks: {summary.chunk_count}",
    ]
    if summary.tasks_due_week:
        lines.append("")
        lines.append("Due this week:")
        lines.extend(f"  • {t}" for t in summary.tasks_due_week)
    else:
        lines.append("")
        lines.append("No tasks due this week.")
    if summary.next_event:
        lines.append("")
        lines.append(f"Next event: {summary.next_event}")
    return "\n".join(lines)
