"""Tests for Kosistenz structured context + life snapshot formatting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cluny.kosistenz_context import (
    AnalyticsSnapshot,
    DEFAULT_KOSISTENZ_INSTRUCTION,
    GoalProgress,
    KosistenzContext,
    format_analytics_snapshot,
    format_kosistenz_context,
    merge_context,
    parse_kosistenz_context,
    read_life_snapshot_file,
    resolve_context_json,
)
from cluny.kosistenz_context import format_chat_question


FULL_SNAPSHOT = {
    "instruction": "Never pick HH:MM; do not treat Cluny tasks/calendar as live.",
    "date": "2026-09-09",
    "week_start": "2026-09-08",
    "week_end": "2026-09-14",
    "todos_today": [{"title": "Spanish review", "due": "2026-09-09"}],
    "overdue": [{"title": "Essay outline"}],
    "unplaced": [{"title": "Gym session"}],
    "free_minutes": 95,
    "journal": "kind=morning_brief\nFocus: ship pack today.",
    "work": {
        "today": [{"title": "Spanish review"}],
        "backlog": [{"title": "Read chapter 4"}],
    },
    "calendar": {
        "days": [
            {
                "date": "2026-09-09",
                "hard_events": [{"title": "Lecture"}],
                "placed": [],
                "unplaced": [{"title": "Gym session"}],
            }
        ]
    },
    "goals": [{"title": "Ship pack", "percent": 40}],
    "briefs": [{"slot": "morning", "focus": ["a"]}],
    "deadline_todos": [{"title": "Send agenda", "due": "2026-09-12"}],
    "events_today": [{"title": "Product sync", "start": "14:00"}],
    "weekly_goals": ["Ship pack"],
    "analytics": {"period": "2026-W37", "tasks_completed": 4},
}


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
    assert DEFAULT_KOSISTENZ_INSTRUCTION.split(";")[0] in text or "Never pick HH:MM" in text


def test_full_snapshot_not_stripped():
    parsed = parse_kosistenz_context(FULL_SNAPSHOT)
    assert parsed is not None
    dumped = parsed.model_dump()
    assert dumped.get("todos_today")
    assert dumped.get("unplaced")
    assert dumped.get("free_minutes") == 95
    assert dumped.get("journal")
    text = format_kosistenz_context(FULL_SNAPSHOT)
    assert "Spanish review" in text
    assert "Gym session" in text
    assert "95" in text
    assert "ship pack today" in text
    assert "Never pick HH:MM" in text


def test_chat_prompt_includes_rich_snapshot():
    prompt = format_chat_question(
        "What's due today?",
        context_json=FULL_SNAPSHOT,
    )
    assert "Context from Kosistenz:" in prompt
    assert "Spanish review" in prompt
    assert "free_minutes" in prompt.lower() or "95" in prompt
    assert "ship pack today" in prompt


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
    assert "Ship pack (60.0%)" in text


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
            "free_minutes": 40,
        }
    )
    assert parsed is not None
    assert parsed.date == "2026-09-01"
    assert parsed.analytics is not None
    assert parsed.analytics.tasks_completed == 3
    assert parsed.model_dump().get("free_minutes") == 40


def test_resolve_from_snapshot_file(tmp_path: Path):
    snap = tmp_path / "life.json"
    snap.write_text('{"date":"2026-09-09","todos_today":[{"title":"A"}]}', encoding="utf-8")
    with patch("cluny.kosistenz_context.fetch_life_snapshot_http", return_value=None):
        with patch("cluny.kosistenz_context.snapshot_path", return_value=snap):
            data = resolve_context_json(None)
    assert data is not None
    assert data["todos_today"][0]["title"] == "A"


def test_read_missing_snapshot_returns_none(tmp_path: Path):
    assert read_life_snapshot_file(tmp_path / "missing.json") is None
