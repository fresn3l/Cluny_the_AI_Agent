"""HTTP helpers for Kosistenz Brain tab (library, sessions, user config, file ingest)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cluny.config import Settings
from cluny.documents import add_file, delete_document
from cluny.extract import ExtractionError
from cluny.library_db import (
    connect,
    document_count,
    get_collections_for_doc,
    inline_source_from_path,
    list_collections,
    list_documents,
    list_inline_sources,
    resolve_document,
)
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.sessions import (
    connect as sessions_connect,
    create_session,
    get_session,
    list_messages,
    list_sessions,
)
from cluny.store import get_collection
from cluny.user_config import load_user_config, save_user_config


def stats_payload(settings: Settings) -> dict[str, Any]:
    doc_count = 0
    chunk_count = 0
    try:
        conn = connect(settings)
        doc_count = document_count(conn)
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        chunk_count = get_collection(settings).count()
    except Exception:  # noqa: BLE001
        pass
    uc = load_user_config(settings)
    return {
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "chat_model": settings.chat_model,
        "embed_model": settings.embed_model,
        "retrieval_k": uc.retrieval_k,
        "hybrid_vector_weight": uc.hybrid_vector_weight,
        "agent_mode": uc.agent_mode,
        "ask_collection": uc.ask_collection,
        "data_dir": str(settings.data_dir),
    }


def user_config_payload(settings: Settings) -> dict[str, Any]:
    uc = load_user_config(settings)
    return {
        "chat_model": uc.chat_model,
        "embed_model": uc.embed_model,
        "retrieval_k": uc.retrieval_k,
        "hybrid_vector_weight": uc.hybrid_vector_weight,
        "agent_mode": uc.agent_mode,
        "ask_collection": uc.ask_collection,
        "standalone_mode": uc.standalone_mode,
    }


def apply_user_config_update(settings: Settings, data: dict[str, Any]) -> dict[str, Any]:
    uc = load_user_config(settings)
    if data.get("chat_model") is not None:
        uc.chat_model = str(data["chat_model"]).strip() or uc.chat_model
    if data.get("embed_model") is not None:
        uc.embed_model = str(data["embed_model"]).strip() or uc.embed_model
    if data.get("retrieval_k") is not None:
        uc.retrieval_k = max(1, int(data["retrieval_k"]))
    if data.get("hybrid_vector_weight") is not None:
        w = float(data["hybrid_vector_weight"])
        uc.hybrid_vector_weight = max(0.0, min(1.0, w))
    if data.get("agent_mode") is not None:
        uc.agent_mode = str(data["agent_mode"])
    if data.get("ask_collection") is not None:
        uc.ask_collection = str(data["ask_collection"])
    if data.get("standalone_mode") is not None:
        uc.standalone_mode = bool(data["standalone_mode"])
    save_user_config(settings, uc)
    return user_config_payload(settings)


def library_collections(settings: Settings) -> dict[str, Any]:
    conn = connect(settings)
    collections = list_collections(conn)
    sources = list_inline_sources(conn)
    conn.close()
    return {"collections": collections, "sources": sources}


def library_documents_payload(
    settings: Settings,
    *,
    collection: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    conn = connect(settings)
    docs = list_documents(conn, collection=collection, source=source)
    payload = []
    for d in docs:
        colls = get_collections_for_doc(conn, d.id)
        payload.append(
            {
                "id": d.id,
                "path": d.path,
                "kind": d.kind,
                "title": d.title,
                "chunk_count": d.chunk_count,
                "source": inline_source_from_path(d.path),
                "collections": colls,
            }
        )
    conn.close()
    return {"documents": payload, "collection": collection, "source": source}


def delete_library_doc(settings: Settings, doc_id: str) -> dict[str, Any]:
    conn = connect(settings)
    doc = resolve_document(conn, doc_id)
    conn.close()
    if doc is None:
        raise ValueError(f"No document matching: {doc_id!r}")
    collection = get_collection(settings)
    deleted = delete_document(settings, collection, doc.id)
    return {"deleted": True, "doc_id": deleted}


def sessions_list(settings: Settings, *, limit: int = 50) -> dict[str, Any]:
    conn = sessions_connect(settings)
    rows = list_sessions(conn, limit=limit)
    conn.close()
    return {
        "sessions": [
            {
                "id": r.id,
                "title": r.title,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]
    }


def session_messages_payload(settings: Settings, session_id: str) -> dict[str, Any]:
    conn = sessions_connect(settings)
    if get_session(conn, session_id) is None:
        conn.close()
        raise ValueError(f"Unknown session_id: {session_id}")
    msgs = list_messages(conn, session_id)
    conn.close()
    return {
        "session_id": session_id,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at} for m in msgs
        ],
    }


def create_session_payload(settings: Settings, title: str | None = None) -> dict[str, Any]:
    conn = sessions_connect(settings)
    sid = create_session(conn, title=title)
    conn.close()
    return {"session_id": sid, "title": title}


def ingest_uploaded_file(
    settings: Settings,
    *,
    filename: str,
    content: bytes,
    title: str | None = None,
    copy_into_library: bool = False,
    collection: str | None = None,
) -> dict[str, Any]:
    suffix = Path(filename or "upload").suffix or ".txt"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        chroma = get_collection(settings)
        ollama = OllamaClient(settings)
        result = add_file(
            settings,
            chroma,
            ollama,
            tmp_path,
            copy_into_library=copy_into_library,
            title=title or Path(filename).stem or None,
        )
        if collection and collection.strip():
            from cluny.library_db import add_doc_to_collection, connect as lib_connect

            conn = lib_connect(settings)
            add_doc_to_collection(conn, result.doc_id, collection.strip())
            conn.close()
        return {
            "doc_id": result.doc_id,
            "chunk_count": result.chunk_count,
            "unchanged": result.unchanged,
        }
    except (ExtractionError, OllamaError) as e:
        raise ValueError(str(e)) from e
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
