"""Structured work proposals for Kosistenz (no scheduling)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from cluny.config import Settings
from cluny.kosistenz_context import KosistenzContext
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.query import RetrievedChunk, retrieve
from cluny.supervisor import format_chat_question

PROPOSE_SYSTEM = (
    "You suggest work items for the user. Kosistenz owns the calendar and week clock — "
    "you only propose work, never pick clock times or days.\n"
    "Use the live Kosistenz context and any retrieved journal/analytics snippets from "
    "indexed history. Ground proposals in patterns you see (missed goals, slipped tasks, "
    "journal themes) when relevant.\n"
    "Reply with ONLY valid JSON, no markdown:\n"
    '{"proposals": [{"title": "string", "estimate_minutes": number or null, '
    '"due": "YYYY-MM-DD or null", "keywords": ["string"]}]}\n'
    "Use an empty proposals array if nothing to suggest."
)

RETRIEVED_SNIPPETS_HEADER = "Retrieved from indexed journals and analytics:"


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


def format_retrieved_snippets(chunks: list[RetrievedChunk]) -> str | None:
    if not chunks:
        return None
    lines = [RETRIEVED_SNIPPETS_HEADER]
    for i, ch in enumerate(chunks, start=1):
        lines.append(f"[{i}] {ch.label}\n{ch.text[:600]}")
    return "\n\n".join(lines)


def _build_proposal_user_prompt(
    question: str,
    *,
    context: str | None = None,
    context_json: KosistenzContext | dict | None = None,
    retrieved_block: str | None = None,
) -> str:
    user = format_chat_question(question, context, context_json=context_json)
    if retrieved_block:
        user = f"{retrieved_block}\n\n{user}"
    return user


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
    context_json: KosistenzContext | dict | None = None,
    settings: Settings | None = None,
    collection: str | None = None,
    k: int = 5,
) -> list[WorkProposal]:
    """Return structured work proposals grounded in Kosistenz context + indexed history."""
    settings = settings or Settings.load()
    chunks = retrieve(
        question,
        k=k,
        settings=settings,
        collection_name=collection,
    )
    retrieved_block = format_retrieved_snippets(chunks)
    user = _build_proposal_user_prompt(
        question,
        context=context,
        context_json=context_json,
        retrieved_block=retrieved_block,
    )
    ollama = OllamaClient(settings)
    raw = ollama.chat(system=PROPOSE_SYSTEM, user=user)
    try:
        return _parse_proposals(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise OllamaError(f"Could not parse proposal JSON: {e}") from e
