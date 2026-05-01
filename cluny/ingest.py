"""Ingest text into chunked embeddings."""

from __future__ import annotations

import hashlib
from pathlib import Path

from chromadb.api.models.Collection import Collection

from cluny.chunking import chunk_text
from cluny.ollama_client import OllamaClient


def _source_id(text: str, label: str) -> str:
    h = hashlib.sha256(f"{label}\0{text}".encode("utf-8")).hexdigest()[:16]
    return f"{label}:{h}"


def ingest_string(
    collection: Collection,
    ollama: OllamaClient,
    text: str,
    source_label: str,
    max_chars: int = 1200,
    overlap: int = 200,
    extra_metadata: dict[str, str] | None = None,
) -> int:
    """Chunk, embed, and upsert. Returns number of chunks stored."""
    parts = chunk_text(text, max_chars=max_chars, overlap=overlap)
    if not parts:
        return 0

    base = _source_id(text, source_label)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str | int]] = []
    embeddings: list[list[float]] = []

    for i, part in enumerate(parts):
        ids.append(f"{base}:{i}")
        documents.append(part)
        meta: dict[str, str | int] = {"source": source_label, "chunk_index": i}
        if extra_metadata:
            for key, val in extra_metadata.items():
                meta[key] = val
        metadatas.append(meta)
        embeddings.append(ollama.embed(part))

    collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    return len(parts)


def read_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
