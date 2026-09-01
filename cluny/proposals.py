"""Structured work proposals for Kosistenz (no scheduling)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from cluny.config import Settings
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.supervisor import format_chat_question

PROPOSE_SYSTEM = (
    "You suggest work items for the user. Kosistenz owns the calendar and week clock — "
    "you only propose work, never pick clock times or days.\n"
    "Reply with ONLY valid JSON, no markdown:\n"
    '{"proposals": [{"title": "string", "estimate_minutes": number or null, '
    '"due": "YYYY-MM-DD or null", "keywords": ["string"]}]}\n'
    "Use an empty proposals array if nothing to suggest."
)


@dataclass(frozen=True)
class WorkProposal:
    title: str
    estimate_minutes: int | None
    due: str | None
    keywords: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "estimate_minutes": self.estimate_minutes,
            "due": self.due,
            "keywords": self.keywords,
        }


def _parse_proposals(raw: str) -> list[WorkProposal]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    data = json.loads(text)
    items = data.get("proposals") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    out: list[WorkProposal] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        est = item.get("estimate_minutes")
        estimate = int(est) if isinstance(est, (int, float)) else None
        due_raw = item.get("due")
        due = str(due_raw).strip() if due_raw else None
        kw = item.get("keywords") or []
        keywords = [str(k) for k in kw if str(k).strip()] if isinstance(kw, list) else []
        out.append(
            WorkProposal(
                title=title,
                estimate_minutes=estimate,
                due=due,
                keywords=keywords,
            )
        )
    return out


def run_proposals(
    question: str,
    *,
    context: str | None = None,
    settings: Settings | None = None,
) -> list[WorkProposal]:
    """Return structured work proposals for Kosistenz to accept/schedule."""
    settings = settings or Settings.load()
    user = format_chat_question(question, context)
    ollama = OllamaClient(settings)
    raw = ollama.chat(system=PROPOSE_SYSTEM, user=user)
    try:
        return _parse_proposals(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise OllamaError(f"Could not parse proposal JSON: {e}") from e
