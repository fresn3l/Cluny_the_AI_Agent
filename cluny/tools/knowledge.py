"""Knowledge tools: search_brain and add_note."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from cluny.config import Settings
from cluny.ingest import ingest_string
from cluny.library_db import connect, replace_chunks, upsert_document
from cluny.ollama_client import OllamaClient
from cluny.query import retrieve
from cluny.store import get_collection
from cluny.tools.registry import Tool


def _search_brain(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}
    k = int(args.get("k", 5))
    chunks = retrieve(query, k=k, settings=settings)
    return {
        "results": [
            {
                "label": c.label,
                "doc_path": c.doc_path,
                "chunk_index": c.chunk_index,
                "text": c.text[:2000],
                "score": round(c.score, 4),
            }
            for c in chunks
        ]
    }


def _add_note(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    text = str(args.get("text", "")).strip()
    if not text:
        return {"error": "text is required"}
    title = str(args.get("title", "agent-note")).strip() or "agent-note"

    collection = get_collection(settings)
    ollama = OllamaClient(settings)
    doc_id = uuid.uuid4().hex
    chash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = f"agent://note/{doc_id}"

    conn = connect(settings)
    n, parts = ingest_string(
        collection,
        ollama,
        text,
        source_label=title,
        extra_metadata={"doc_id": doc_id, "kind": "note"},
        return_chunks=True,
    )
    replace_chunks(conn, doc_id, parts)
    upsert_document(
        conn,
        doc_id,
        path,
        "note",
        title,
        chash,
        len(text.encode("utf-8")),
        n,
    )
    conn.close()
    return {"doc_id": doc_id, "title": title, "chunks": n}


def build_knowledge_tools(settings: Settings) -> list[Tool]:
    return [
        Tool(
            name="search_brain",
            description=(
                "Search the user's indexed notes and documents. Use when you need "
                "facts from their second brain before answering."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {
                        "type": "integer",
                        "description": "Number of chunks to retrieve (default 5)",
                    },
                },
                "required": ["query"],
            },
            handler=lambda args: _search_brain(args, settings),
        ),
        Tool(
            name="add_note",
            description=(
                "Save a short note into the user's indexed second brain. "
                "Use for captures the user explicitly asks to remember."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Note content"},
                    "title": {"type": "string", "description": "Short title for the note"},
                },
                "required": ["text"],
            },
            handler=lambda args: _add_note(args, settings),
        ),
    ]


KNOWLEDGE_TOOLS: list[Tool] = []
