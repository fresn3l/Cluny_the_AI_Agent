"""Structured work proposals for Kosistenz (no scheduling)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from cluny.brain_config import DEFAULT_PROMPTS, get_max_proposals, get_prompt
from cluny.config import Settings
from cluny.kosistenz_context import KosistenzContext, format_chat_question, resolve_context_json
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.proposal_accepts import accepted_proposal_ids
from cluny.query import RetrievedChunk, RagSource, retrieve

PROPOSE_SYSTEM = DEFAULT_PROMPTS["propose_system"]

RETRIEVED_SNIPPETS_HEADER = "Retrieved from indexed journals and analytics:"

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_TIME_TAIL_RE = re.compile(
    r"\s+(?:at\s+)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm|AM|PM)?\s*$"
)


@dataclass(frozen=True)
class ProposalCitation:
    title: str
    locator: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"title": self.title}
        if self.locator:
            out["locator"] = self.locator
        return out


@dataclass(frozen=True)
class WorkProposal:
    title: str
    estimate_minutes: int | None
    due: str | None
    keywords: list[str]
    id: str = ""
    citations: list[ProposalCitation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(
                self,
                "id",
                stable_proposal_id(
                    title=self.title,
                    due=self.due,
                    keywords=list(self.keywords),
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "estimate_minutes": self.estimate_minutes,
            "due": self.due,
            "keywords": self.keywords,
            "citations": [c.to_dict() for c in self.citations],
        }


@dataclass(frozen=True)
class ProposalResult:
    proposals: list[WorkProposal]
    sources: tuple[RagSource, ...]


def normalize_due(raw: Any) -> str | None:
    """Keep calendar day only (YYYY-MM-DD). Strip clock times."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in ("null", "none"):
        return None
    text = _TIME_TAIL_RE.sub("", text).strip()
    # ISO datetime → date
    if "T" in text:
        text = text.split("T", 1)[0].strip()
    if " " in text and _DATE_RE.match(text):
        text = text.split(" ", 1)[0].strip()
    m = _DATE_RE.match(text)
    if m:
        return m.group(1)
    # Reject anything that still looks like a clock time
    if re.search(r"\d{1,2}:\d{2}", text):
        return None
    return None


def stable_proposal_id(
    *,
    title: str,
    due: str | None,
    keywords: list[str],
    explicit_id: str | None = None,
) -> str:
    if explicit_id and str(explicit_id).strip():
        return str(explicit_id).strip()
    key = "|".join(
        [
            title.strip().casefold(),
            due or "",
            ",".join(k.strip().casefold() for k in keywords if str(k).strip()),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def chunks_to_sources(chunks: list[RetrievedChunk], preview_len: int = 450) -> tuple[RagSource, ...]:
    sources: list[RagSource] = []
    for i, ch in enumerate(chunks):
        snippet = ch.text.strip().replace("\n", " ")
        if len(snippet) > preview_len:
            snippet = snippet[: preview_len - 1] + "…"
        sources.append(
            RagSource(
                label=ch.label or f"chunk {i + 1}",
                snippet=snippet,
                doc_path=ch.doc_path,
                chunk_index=ch.chunk_index,
            )
        )
    return tuple(sources)


def source_dicts_from_rag_sources(sources: tuple[RagSource, ...]) -> list[dict[str, Any]]:
    return [
        {
            "label": s.label,
            "snippet": s.snippet,
            "doc_path": s.doc_path,
            "chunk_index": s.chunk_index,
        }
        for s in sources
    ]


def format_retrieved_snippets(chunks: list[RetrievedChunk]) -> str | None:
    if not chunks:
        return None
    lines = [RETRIEVED_SNIPPETS_HEADER]
    for i, ch in enumerate(chunks, start=1):
        lines.append(f"[{i}] {ch.label}\n{ch.text[:600]}")
    return "\n\n".join(lines)


def _citations_from_item(item: dict[str, Any], fallback_chunks: list[RetrievedChunk]) -> list[ProposalCitation]:
    raw = item.get("citations")
    out: list[ProposalCitation] = []
    if isinstance(raw, list):
        for c in raw:
            if isinstance(c, dict):
                title = str(c.get("title") or c.get("label") or "").strip()
                if not title:
                    continue
                locator = c.get("locator") or c.get("snippet") or c.get("doc_path")
                out.append(
                    ProposalCitation(
                        title=title,
                        locator=str(locator).strip() if locator else None,
                    )
                )
            elif isinstance(c, str) and c.strip():
                out.append(ProposalCitation(title=c.strip()))
    if out:
        return out
    # Fall back to top retrieved chunks as soft citations
    for ch in fallback_chunks[:2]:
        out.append(
            ProposalCitation(
                title=ch.label or "indexed note",
                locator=(ch.doc_path or ch.text[:80] or None),
            )
        )
    return out


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


def _parse_proposals(
    raw: str,
    *,
    fallback_chunks: list[RetrievedChunk] | None = None,
) -> list[WorkProposal]:
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
    chunks = fallback_chunks or []
    out: list[WorkProposal] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        est = item.get("estimate_minutes")
        estimate = int(est) if isinstance(est, (int, float)) else None
        due = normalize_due(item.get("due"))
        kw = item.get("keywords") or []
        keywords = [str(k).strip() for k in kw if str(k).strip()] if isinstance(kw, list) else []
        citations = _citations_from_item(item, chunks)
        pid = stable_proposal_id(
            title=title,
            due=due,
            keywords=keywords,
            explicit_id=str(item.get("id") or "").strip() or None,
        )
        out.append(
            WorkProposal(
                id=pid,
                title=title,
                estimate_minutes=estimate,
                due=due,
                keywords=keywords,
                citations=citations,
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
) -> ProposalResult:
    """Return structured work proposals grounded in Kosistenz context + indexed history."""
    settings = settings or Settings.load()
    resolved = resolve_context_json(context_json)
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
        context_json=resolved,
        retrieved_block=retrieved_block,
    )
    ollama = OllamaClient(settings)
    raw = ollama.chat(system=get_prompt("propose_system", settings=settings), user=user)
    try:
        proposals = _parse_proposals(raw, fallback_chunks=chunks)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise OllamaError(f"Could not parse proposal JSON: {e}") from e

    skip = accepted_proposal_ids(settings)
    if skip:
        proposals = [p for p in proposals if p.id not in skip]

    limit = get_max_proposals(settings=settings)
    return ProposalResult(
        proposals=proposals[:limit],
        sources=chunks_to_sources(chunks),
    )
