"""Phone / Telegram capture into the Cluny library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cluny.config import Settings
from cluny.documents import IndexResult, add_inline_text
from cluny.extract import ExtractionError
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.store import get_collection


@dataclass(frozen=True)
class CaptureResult:
    doc_id: str
    chunk_count: int
    title: str
    unchanged: bool
    source: str
    collection: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "doc_id": self.doc_id,
            "chunk_count": self.chunk_count,
            "title": self.title,
            "unchanged": self.unchanged,
            "source": self.source,
            "collection": self.collection,
        }


def default_capture_title(*, when: datetime | None = None) -> str:
    ts = when or datetime.now(timezone.utc)
    local = ts.astimezone()
    return local.strftime("%Y-%m-%d %H:%M capture")


def capture_note(
    text: str,
    *,
    settings: Settings | None = None,
    title: str | None = None,
    source: str | None = None,
    collection: str | None = None,
) -> CaptureResult:
    """Index a short note for RAG (phone/Telegram capture)."""
    settings = settings or Settings.load()
    body = text.strip()
    if not body:
        raise ValueError("Note text cannot be empty.")

    src = (source or settings.capture_source).strip() or settings.capture_source
    coll = collection if collection is not None else settings.capture_collection
    coll_name = coll.strip() if coll else None
    display_title = (title.strip() if title else None) or default_capture_title()

    chroma = get_collection(settings)
    ollama = OllamaClient(settings)
    try:
        result: IndexResult = add_inline_text(
            settings,
            chroma,
            ollama,
            body,
            source_label=src,
            title=display_title,
            collection_name=coll_name,
        )
    except ExtractionError as e:
        raise ValueError(str(e)) from e
    except OllamaError:
        raise

    return CaptureResult(
        doc_id=result.doc_id,
        chunk_count=result.chunk_count,
        title=display_title,
        unchanged=result.unchanged,
        source=src,
        collection=coll_name,
    )
