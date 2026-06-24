"""Shared retrieval + generation used by CLI ``ask`` and the desktop UI."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from cluny.config import Settings
from cluny.library_db import connect, fts_search, get_chunk_with_meta
from cluny.ollama_client import OllamaClient
from cluny.store import get_collection, query_raw

EMPTY_INDEX_MESSAGE = (
    "No documents in the index yet. Use `cluny add`, `cluny add-dir`, or `cluny ingest-text` first."
)

SYSTEM_PROMPT = (
    "You are Cluny, a local second-brain assistant. Answer using only the provided "
    "context snippets from the user's indexed notes. If the answer is not in the context, "
    "say you do not have that information in the indexed notes. Be concise. Cite which "
    "snippet supports each claim when possible. Do not invent facts or claim you searched "
    "the internet. If you are uncertain, say so rather than guessing."
)

RAG_USER_TEMPLATE = "Context from indexed notes:\n\n{context}\n\nQuestion: {question}"


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

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    return [
        RetrievedChunk(
            text=texts[key],
            label=labels[key],
            doc_path=paths[key],
            chunk_index=key[1],
            score=score,
        )
        for key, score in ranked
    ]


def retrieve(
    question: str,
    *,
    k: int = 5,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Hybrid vector + FTS retrieval shared by ask, search, and agent tools."""
    settings = settings or Settings.from_env()
    collection = get_collection(settings)
    ollama = OllamaClient(settings)
    pool = max(k, settings.retrieval_k)

    q_emb = ollama.embed(question)
    raw = query_raw(collection, q_emb, n_results=pool)

    docs = (raw.get("documents") or [[]])[0]
    metas = (raw.get("metadatas") or [[]])[0]

    vector_ranked: list[tuple[str, int, str, str, str | None]] = []
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
        label = src or f"chunk {i + 1}"
        vector_ranked.append((doc_id, chunk_index, doc, label, doc_path))

    conn = connect(settings)
    if vector_ranked:
        for idx, (doc_id, chunk_index, text, label, _) in enumerate(vector_ranked):
            if doc_id:
                meta = get_chunk_with_meta(conn, doc_id, chunk_index)
                if meta:
                    doc_path, title, _ = meta
                    label = title or label
                    vector_ranked[idx] = (doc_id, chunk_index, text, label, doc_path)
    fts_rows = fts_search(conn, question, limit=pool)
    fts_ranked: list[tuple[str, int, str, str, str | None]] = []
    for doc_id, chunk_index, text in fts_rows:
        meta = get_chunk_with_meta(conn, doc_id, chunk_index)
        if meta:
            doc_path, title, _ = meta
            label = title or doc_path
        else:
            doc_path, label = None, doc_id[:8]
        fts_ranked.append((doc_id, chunk_index, text, label, doc_path))
    conn.close()

    if not vector_ranked and not fts_ranked:
        return []

    if not fts_ranked:
        return [
            RetrievedChunk(text=t, label=l, doc_path=p, chunk_index=ci, score=1.0 / (i + 1))
            for i, (_, ci, t, l, p) in enumerate(vector_ranked[:k])
        ]

    return _rrf_merge(vector_ranked, fts_ranked, k=k, vector_weight=settings.hybrid_vector_weight)


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
) -> RagAnswer:
    """
    Retrieve chunks, call Ollama chat. Raises ``OllamaError`` on network/model failures.
    """
    settings = settings or Settings.from_env()
    chunks = retrieve(question, k=k, settings=settings)

    if not chunks:
        return RagAnswer(
            answer=EMPTY_INDEX_MESSAGE,
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
) -> tuple[Iterator[str], tuple[RagSource, ...], bool]:
    """
    Stream answer tokens. Returns (token_iterator, sources, empty_index).
    On empty index, iterator yields the empty message once.
    """
    settings = settings or Settings.from_env()
    chunks = retrieve(question, k=k, settings=settings)

    if not chunks:
        def _empty() -> Iterator[str]:
            yield EMPTY_INDEX_MESSAGE

        return _empty(), (), True

    context, sources = _chunks_to_sources(chunks)
    user = RAG_USER_TEMPLATE.format(context=context, question=question)
    ollama = OllamaClient(settings)
    return ollama.chat_stream(system=SYSTEM_PROMPT, user=user), sources, False


__all__ = [
    "EMPTY_INDEX_MESSAGE",
    "RagAnswer",
    "RagSource",
    "RetrievedChunk",
    "SYSTEM_PROMPT",
    "rag_answer",
    "rag_answer_stream",
    "retrieve",
]
