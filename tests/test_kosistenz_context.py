"""Tests for Kosistenz structured context."""

from __future__ import annotations

from cluny.kosistenz_context import (
    KosistenzContext,
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


def test_merge_context_text_and_json():
    ctx = KosistenzContext(weekly_goals=["Focus"])
    merged = merge_context(context="Extra note", context_json=ctx)
    assert "Focus" in merged
    assert "Extra note" in merged


def test_parse_context_from_dict():
    parsed = parse_kosistenz_context({"date": "2026-09-01", "weekly_goals": ["a"]})
    assert parsed is not None
    assert parsed.date == "2026-09-01"
