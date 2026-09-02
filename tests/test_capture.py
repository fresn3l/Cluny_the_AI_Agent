"""Tests for phone/Telegram capture."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from cluny.capture import CaptureResult, capture_note, default_capture_title
from cluny.documents import IndexResult


def test_default_capture_title_uses_local_time():
    when = datetime(2026, 9, 2, 19, 6, tzinfo=timezone.utc)
    title = default_capture_title(when=when)
    assert title.endswith("capture")
    assert "2026-09-02" in title


def test_capture_note_empty_raises(settings):
    with pytest.raises(ValueError, match="empty"):
        capture_note("   ", settings=settings)


def test_capture_note_success(settings):
    with patch("cluny.capture.add_inline_text") as mock_add:
        mock_add.return_value = IndexResult(doc_id="d1", chunk_count=2, unchanged=False)
        result = capture_note("Met with design team", settings=settings)
    assert isinstance(result, CaptureResult)
    assert result.doc_id == "d1"
    assert result.chunk_count == 2
    assert result.source == settings.capture_source
    assert result.collection == settings.capture_collection
    mock_add.assert_called_once()


def test_capture_note_uses_custom_source(settings):
    with patch("cluny.capture.add_inline_text") as mock_add:
        mock_add.return_value = IndexResult(doc_id="d1", chunk_count=1, unchanged=False)
        capture_note("note", settings=settings, source="phone-capture", collection="journal")
    kwargs = mock_add.call_args.kwargs
    assert kwargs["source_label"] == "phone-capture"
    assert kwargs["collection_name"] == "journal"
