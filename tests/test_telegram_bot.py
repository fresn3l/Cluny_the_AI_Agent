"""Tests for Telegram capture bot helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cluny.capture import CaptureResult
from cluny.telegram_bot import format_capture_reply, handle_message_text, is_allowed_user


def test_is_allowed_user():
    allowed = frozenset({12345})
    assert is_allowed_user(12345, allowed)
    assert not is_allowed_user(999, allowed)
    assert not is_allowed_user(None, allowed)
    assert not is_allowed_user(12345, frozenset())


def test_handle_message_text_help():
    reply = handle_message_text("/help")
    assert "Send any text message" in reply


def test_handle_message_text_capture(settings):
    fake = CaptureResult(
        doc_id="d1",
        chunk_count=2,
        title="2026-09-02 capture",
        unchanged=False,
        source="telegram-capture",
        collection="capture",
    )
    with patch("cluny.telegram_bot.capture_note", return_value=fake):
        reply = handle_message_text("Remember to ship pack", settings=settings)
    assert "Indexed 2 chunk" in reply


def test_format_capture_reply_unchanged():
    result = CaptureResult(
        doc_id="d1",
        chunk_count=1,
        title="t",
        unchanged=True,
        source="telegram-capture",
        collection="capture",
    )
    assert "Already indexed" in format_capture_reply(result)
