"""Shared retrieval + generation used by CLI ``ask`` and the desktop UI."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass

from cluny.config import Settings
from cluny.library_db import connect, doc_ids_in_collection, fts_search, get_chunk_with_meta
from cluny.ollama_client import OllamaClient
from cluny.store import get_collection, query_raw

EMPTY_INDEX_MESSAGE = (
    "No documents in the index yet. Use `cluny add`, `cluny add-dir`, or `cluny ingest-text` first."
)

EMPTY_COLLECTION_MESSAGE = (
    "No documents in that collection yet. Add files with `cluny collection add`, "
    "or choose a different collection."
)

_CROSS_ENCODER = None
_CROSS_ENCODER_LOCK = threading.Lock()

SYSTEM_PROMPT = (
    "You are Cluny, a local second-brain assistant. Answer using only the provided "
    "context snippets from the user's indexed notes. If the answer is not in the context, "
    "say you do not have that information in the indexed notes. Be concise. Cite which "
    "snippet supports each claim when possible. Do not invent facts or claim you searched "
    "the internet. If you are uncertain, say so rather than guessing."
)

RAG_USER_TEMPLATE = "Context from indexed notes:\n\n{context}\n\nQuestion: {question}"

RERANK_SYSTEM = (
    "Score how relevant each numbered snippet is to the question on a scale of 0-10. "
    "Reply with ONLY comma-separated scores in snippet order (e.g. 8,3,9). No other text."
)


@dataclass(frozen=True)
class RagSource:
    """One retrieved chunk shown for citations in the UI."""

    label: str
    snippet: str
    doc_path: str | None = None
    chunk_index: int | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    """One ranked chunk from hybrid retrieval."""

    text: str
    label: str
    doc_path: str | None
    chunk_index: int | None
    score: float
    doc_id: str = ""


@dataclass(frozen=True)
class RagAnswer:
    """Model reply plus optional source previews."""

    answer: str
    sources: tuple[RagSource, ...]
    empty_index: bool


def _rrf_merge(
    vector_ranked: list[tuple[str, int, str, str, str | None]],
    fts_ranked: list[tuple[str, int, str, str, str | None]],
    *,
    k: int,
    vector_weight: float,
) -> list[RetrievedChunk]:
    """Reciprocal rank fusion of vector and FTS results."""
    rrf_k = 60
    scores: dict[tuple[str, int], float] = {}
    texts: dict[tuple[str, int], str] = {}
    labels: dict[tuple[str, int], str] = {}
    paths: dict[tuple[str, int], str | None] = {}

    for rank, (doc_id, chunk_index, text, label, doc_path) in enumerate(vector_ranked):
        key = (doc_id, chunk_index)
        scores[key] = scores.get(key, 0.0) + vector_weight / (rrf_k + rank + 1)
        texts[key] = text
        labels[key] = label
        paths[key] = doc_path

    fts_weight = 1.0 - vector_weight
    for rank, (doc_id, chunk_index, text, label, doc_path) in enumerate(fts_ranked):
        key = (doc_id, chunk_index)
        scores[key] = scores.get(key, 0.0) + fts_weight / (rrf_k + rank + 1)
        texts.setdefault(key, text)
        labels.setdefault(key, label)
        paths.setdefault(key, doc_path)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        RetrievedChunk(
            text=texts[key],
            label=labels[key],
            doc_path=paths[key],
            chunk_index=key[1],
            score=score,
            doc_id=key[0],
        )
        for key, score in ranked[:k]
    ]


def _llm_rerank(
    chunks: list[RetrievedChunk],
    question: str,
    *,
    k: int,
    settings: Settings,
) -> list[RetrievedChunk]:
    """Re-score top pool chunks with a short LLM prompt."""
    if len(chunks) <= k:
        return chunks
    ollama = OllamaClient(settings)
    lines = []
    for i, ch in enumerate(chunks):
        preview = ch.text[:400].replace("\n", " ")
        lines.append(f"[{i + 1}] {preview}")
    user = f"Question: {question}\n\nSnippets:\n" + "\n\n".join(lines)
    try:
        raw = ollama.chat(system=RERANK_SYSTEM, user=user)
    except Exception:  # noqa: BLE001
        return chunks[:k]
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", raw)]
    if len(nums) != len(chunks):
        return chunks[:k]
    scored = sorted(zip(chunks, nums, strict=False), key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored[:k]]


def _get_cross_encoder():
    """Load cross-encoder once per process (avoids cold-start on every rerank)."""
    global _CROSS_ENCODER
    if _CROSS_ENCODER is not None:
        return _CROSS_ENCODER
    with _CROSS_ENCODER_LOCK:
        if _CROSS_ENCODER is None:
            from sentence_transformers import CrossEncoder

            _CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        return _CROSS_ENCODER


def _resolve_doc_ids(
    settings: Settings,
    *,
    collection_name: str | None = None,
    doc_ids: frozenset[str] | None = None,
) -> frozenset[str] | None:
    """Merge explicit doc_ids with an optional named collection filter."""
    if not collection_name or not collection_name.strip():
        return doc_ids
    conn = connect(settings)
    coll_ids = doc_ids_in_collection(conn, collection_name.strip())
    conn.close()
    if doc_ids is not None:
        return doc_ids & coll_ids
    return coll_ids


def _empty_rag_message(collection_name: str | None) -> str:
    if collection_name and collection_name.strip():
        return EMPTY_COLLECTION_MESSAGE
    return EMPTY_INDEX_MESSAGE


def _cross_rerank(
    chunks: list[RetrievedChunk],
    question: str,
    *,
    k: int,
) -> list[RetrievedChunk]:
    """Re-score chunks with a local cross-encoder (optional dep)."""
    if len(chunks) <= k:
        return chunks
    try:
        model = _get_cross_encoder()
    except ImportError:
        return chunks[:k]

    pairs = [(question, ch.text[:512]) for ch in chunks]
    scores = model.predict(pairs)
    scored = sorted(zip(chunks, scores, strict=False), key=lambda x: float(x[1]), reverse=True)
    return [c for c, _ in scored[:k]]


def retrieve(
    question: str,
    *,
    k: int = 5,
    settings: Settings | None = None,
    fts_only: bool = False,
    collection_name: str | None = None,
    doc_ids: frozenset[str] | None = None,
) -> list[RetrievedChunk]:
    """Hybrid vector + FTS retrieval shared by ask, search, and agent tools."""
    settings = settings or Settings.from_env()
    pool = max(k, settings.retrieval_k)
    if settings.rerank_mode in ("llm", "cross"):
        pool = max(pool, k * 3)

    doc_ids = _resolve_doc_ids(
        settings, collection_name=collection_name, doc_ids=doc_ids
    )
    if collection_name and collection_name.strip() and doc_ids is not None and not doc_ids:
        return []

    conn = connect(settings)
    fts_rows = fts_search(conn, question, limit=pool, doc_ids=doc_ids)
    fts_ranked: list[tuple[str, int, str, str, str | None]] = []
    for doc_id, chunk_index, text in fts_rows:
        if doc_ids is not None and doc_id not in doc_ids:
            continue
        meta = get_chunk_with_meta(conn, doc_id, chunk_index)
        if meta:
            doc_path, title, _ = meta
            label = title or doc_path
        else:
            doc_path, label = None, doc_id[:8]
        fts_ranked.append((doc_id, chunk_index, text, label, doc_path))

    vector_ranked: list[tuple[str, int, str, str, str | None]] = []
    if not fts_only:
        collection = get_collection(settings)
        ollama = OllamaClient(settings)
        q_emb = ollama.embed(question)
        raw = query_raw(collection, q_emb, n_results=pool)

        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]

        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            doc_id = ""
            chunk_index = i
            src = ""
            doc_path: str | None = None
            if isinstance(meta, dict):
                doc_id = str(meta.get("doc_id", ""))
                chunk_index = int(meta.get("chunk_index", i))
                src = str(meta.get("source", ""))
                surl = meta.get("source_url")
                if surl:
                    src = f"{src} | {surl}" if src else str(surl)
            if doc_ids is not None and doc_id and doc_id not in doc_ids:
                continue
            label = src or f"chunk {i + 1}"
            if doc_id:
                meta_row = get_chunk_with_meta(conn, doc_id, chunk_index)
                if meta_row:
                    doc_path, title, _ = meta_row
                    label = title or label
            vector_ranked.append((doc_id, chunk_index, doc, label, doc_path))

    conn.close()

    if not vector_ranked and not fts_ranked:
        return []

    if not fts_ranked:
        merged = [
            RetrievedChunk(text=t, label=l, doc_path=p, chunk_index=ci, score=1.0 / (i + 1), doc_id=did)
            for i, (did, ci, t, l, p) in enumerate(vector_ranked[:pool])
        ]
    elif not vector_ranked or fts_only:
        merged = [
            RetrievedChunk(text=t, label=l, doc_path=p, chunk_index=ci, score=1.0 / (i + 1), doc_id=did)
            for i, (did, ci, t, l, p) in enumerate(fts_ranked[:pool])
        ]
    else:
        merged = _rrf_merge(vector_ranked, fts_ranked, k=pool, vector_weight=settings.hybrid_vector_weight)

    if settings.rerank_mode == "llm" and len(merged) > k:
        merged = _llm_rerank(merged, question, k=k, settings=settings)
    elif settings.rerank_mode == "cross" and len(merged) > k:
        merged = _cross_rerank(merged, question, k=k)
    else:
        merged = merged[:k]

    return merged


def _chunks_to_sources(chunks: list[RetrievedChunk], preview_len: int = 450) -> tuple[str, tuple[RagSource, ...]]:
    context_blocks: list[str] = []
    sources: list[RagSource] = []

    for i, ch in enumerate(chunks):
        prefix = f"[{ch.label}]\n" if ch.label else ""
        context_blocks.append(f"{prefix}{ch.text}")
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

    context = "\n\n---\n\n".join(context_blocks)
    return context, tuple(sources)


def rag_answer(
    question: str,
    *,
    k: int = 5,
    settings: Settings | None = None,
    collection_name: str | None = None,
    doc_ids: frozenset[str] | None = None,
) -> RagAnswer:
    """
    Retrieve chunks, call Ollama chat. Raises ``OllamaError`` on network/model failures.
    """
    settings = settings or Settings.from_env()
    chunks = retrieve(
        question, k=k, settings=settings, collection_name=collection_name, doc_ids=doc_ids
    )

    if not chunks:
        return RagAnswer(
            answer=_empty_rag_message(collection_name),
            sources=(),
            empty_index=True,
        )

    context, sources = _chunks_to_sources(chunks)
    user = RAG_USER_TEMPLATE.format(context=context, question=question)
    ollama = OllamaClient(settings)
    answer = ollama.chat(system=SYSTEM_PROMPT, user=user)

    return RagAnswer(answer=answer, sources=sources, empty_index=False)


def rag_answer_stream(
    question: str,
    *,
    k: int = 5,
    settings: Settings | None = None,
    collection_name: str | None = None,
    doc_ids: frozenset[str] | None = None,
) -> tuple[Iterator[str], tuple[RagSource, ...], bool]:
    """
    Stream answer tokens. Returns (token_iterator, sources, empty_index).
    On empty index, iterator yields the empty message once.
    """
    settings = settings or Settings.from_env()
    chunks = retrieve(
        question,
        k=k,
        settings=settings,
        collection_name=collection_name,
        doc_ids=doc_ids,
    )

    if not chunks:
        msg = _empty_rag_message(collection_name)

        def _empty() -> Iterator[str]:
            yield msg

        return _empty(), (), True

    context, sources = _chunks_to_sources(chunks)
    user = RAG_USER_TEMPLATE.format(context=context, question=question)
    ollama = OllamaClient(settings)
    return ollama.chat_stream(system=SYSTEM_PROMPT, user=user), sources, False


__all__ = [
    "EMPTY_COLLECTION_MESSAGE",
    "EMPTY_INDEX_MESSAGE",
    "RagAnswer",
    "RagSource",
    "RetrievedChunk",
    "SYSTEM_PROMPT",
    "rag_answer",
    "rag_answer_stream",
    "retrieve",
]
