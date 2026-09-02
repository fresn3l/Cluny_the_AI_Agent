"""Telegram bot: text Cluny notes from your phone into the library."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from cluny.capture import CaptureResult, capture_note
from cluny.config import Settings
from cluny.ollama_client import OllamaError

log = logging.getLogger(__name__)

HELP_TEXT = (
    "Send any text message and Cluny will index it for search.\n\n"
    "Commands:\n"
    "/help — this message\n"
    "/start — welcome\n\n"
    "Ask later with: cluny ask \"…\" or the Cluny widget."
)


def _api_base(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def is_allowed_user(user_id: int | None, allowed: frozenset[int]) -> bool:
    if user_id is None:
        return False
    if not allowed:
        return False
    return user_id in allowed


def format_capture_reply(result: CaptureResult) -> str:
    if result.unchanged:
        return f"Already indexed ({result.chunk_count} chunk(s))."
    return f"Indexed {result.chunk_count} chunk(s).\nTitle: {result.title}"


def handle_message_text(
    text: str,
    *,
    settings: Settings | None = None,
) -> str:
    """Process user text; return reply for Telegram."""
    settings = settings or Settings.load()
    stripped = text.strip()
    if not stripped:
        return "Send some text to capture."
    lower = stripped.lower()
    if lower in ("/start", "/help"):
        return HELP_TEXT
    if lower.startswith("/"):
        return "Unknown command. Send plain text to capture a note, or /help."

    try:
        result = capture_note(stripped, settings=settings)
    except ValueError as e:
        return f"Could not capture: {e}"
    except OllamaError as e:
        return f"Brain offline: {e}"
    return format_capture_reply(result)


def send_message(token: str, chat_id: int, text: str, *, timeout: float = 30.0) -> None:
    url = f"{_api_base(token)}/sendMessage"
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json={"chat_id": chat_id, "text": text})
        r.raise_for_status()


def get_updates(
    token: str,
    *,
    offset: int | None = None,
    timeout: int = 50,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    url = f"{_api_base(token)}/getUpdates"
    with httpx.Client(timeout=timeout + 10) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {data}")
    result = data.get("result")
    return list(result) if isinstance(result, list) else []


def run_bot(settings: Settings | None = None) -> None:
    """Long-poll Telegram and index incoming text notes."""
    settings = settings or Settings.load()
    token = settings.telegram_bot_token.strip()
    if not token:
        raise RuntimeError("Set CLUNY_TELEGRAM_BOT_TOKEN in .env")
    if not settings.telegram_allowed_user_ids:
        raise RuntimeError(
            "Set CLUNY_TELEGRAM_ALLOWED_USER_IDS (comma-separated Telegram user ids). "
            "Message @userinfobot on Telegram to learn yours."
        )

    log.info("Cluny Telegram capture bot running (Ctrl+C to stop).")
    offset: int | None = None
    while True:
        try:
            updates = get_updates(token, offset=offset, timeout=50)
        except httpx.HTTPError as e:
            log.warning("Telegram poll error: %s", e)
            time.sleep(3)
            continue

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1

            message = update.get("message") or update.get("edited_message")
            if not isinstance(message, dict):
                continue
            user = message.get("from") or {}
            user_id = user.get("id")
            if not is_allowed_user(int(user_id) if user_id is not None else None, settings.telegram_allowed_user_ids):
                continue

            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue

            text = message.get("text")
            if not isinstance(text, str):
                try:
                    send_message(token, int(chat_id), "Send text notes for now (no photos/voice yet).")
                except httpx.HTTPError as e:
                    log.warning("sendMessage failed: %s", e)
                continue

            reply = handle_message_text(text, settings=settings)
            try:
                send_message(token, int(chat_id), reply)
            except httpx.HTTPError as e:
                log.warning("sendMessage failed: %s", e)
