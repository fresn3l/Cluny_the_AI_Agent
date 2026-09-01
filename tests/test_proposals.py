"""Tests for structured work proposals."""

from __future__ import annotations

from unittest.mock import patch

from cluny.proposals import _parse_proposals, run_proposals


def test_parse_proposals_json():
    raw = '{"proposals": [{"title": "Draft agenda", "estimate_minutes": 25, "due": "2026-09-04", "keywords": ["agenda"]}]}'
    items = _parse_proposals(raw)
    assert len(items) == 1
    assert items[0].title == "Draft agenda"
    assert items[0].estimate_minutes == 25


def test_run_proposals_mocked(settings):
    raw = '{"proposals": [{"title": "Review PR", "estimate_minutes": 30, "due": null, "keywords": []}]}'
    with patch("cluny.proposals.OllamaClient") as mock_cls:
        mock_cls.return_value.chat.return_value = raw
        items = run_proposals("What should I do tomorrow?", settings=settings)
    assert len(items) == 1
    assert items[0].title == "Review PR"
