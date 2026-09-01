"""Tests for Kosistenz structured context."""

from __future__ import annotations

from cluny.kosistenz_context import (
    AnalyticsSnapshot,
    GoalProgress,
    KosistenzContext,
    format_analytics_snapshot,
    format_kosistenz_context,
    merge_context,
    parse_kosistenz_context,
)


def test_format_structured_context():
    ctx = KosistenzContext(
        date="2026-09-01",
        deadline_todos=[{"title": "Send agenda", "due": "2026-09-04"}],
        events_today=[{"title": "Product sync", "start": "14:00"}],
        weekly_goals=["Ship pack"],
    )
    text = format_kosistenz_context(ctx)
    assert "Send agenda" in text
    assert "Product sync" in text
    assert "Ship pack" in text


def test_format_analytics_snapshot():
    snap = AnalyticsSnapshot(
        period="2026-W35",
        tasks_completed=12,
        tasks_slipped=3,
        focus_hours=18.5,
        journal_streak_days=14,
        goal_progress=[GoalProgress(goal="Ship pack", percent=60)],
    )
    text = format_analytics_snapshot(snap)
    assert "2026-W35" in text
    assert "Tasks completed: 12" in text
    assert "Tasks slipped: 3" in text
    assert "Ship pack (60.0%)" in text


def test_context_includes_analytics():
    ctx = KosistenzContext(
        analytics=AnalyticsSnapshot(tasks_completed=5, tasks_slipped=1),
        weekly_goals=["Focus"],
    )
    text = format_kosistenz_context(ctx)
    assert "Analytics snapshot" in text
    assert "Tasks completed: 5" in text
    assert "Focus" in text


def test_merge_context_text_and_json():
    ctx = KosistenzContext(weekly_goals=["Focus"])
    merged = merge_context(context="Extra note", context_json=ctx)
    assert "Focus" in merged
    assert "Extra note" in merged


def test_parse_context_from_dict():
    parsed = parse_kosistenz_context(
        {
            "date": "2026-09-01",
            "weekly_goals": ["a"],
            "analytics": {"period": "2026-W35", "tasks_completed": 3},
        }
    )
    assert parsed is not None
    assert parsed.date == "2026-09-01"
    assert parsed.analytics is not None
    assert parsed.analytics.tasks_completed == 3
