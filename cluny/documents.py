"""Register files in the library DB and index them into Chroma."""

from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from chromadb.api.models.Collection import Collection

from cluny.config import Settings
from cluny.extract import ExtractionError, extract_text
from cluny.ingest import ingest_string
from cluny.library_db import (
    connect,
    delete_chunks_for_doc,
    delete_document_row,
    get_by_path,
    replace_chunks,
    resolve_document,
    upsert_document,
)
from cluny.ollama_client import OllamaClient
from cluny.web_fetch import fetch_and_extract

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexResult:
    doc_id: str
    chunk_count: int
    unchanged: bool = False


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _meta_str(d: dict[str, str]) -> dict[str, str]:
    return {k: str(v) for k, v in d.items()}


def _delete_vectors(collection: Collection, doc_id: str) -> None:
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception as e:  # noqa: BLE001
        log.warning("Chroma delete failed for doc_id=%s: %s", doc_id, e)


def delete_document(
    settings: Settings,
    collection: Collection,
    identifier: str,
    *,
    remove_managed_copy: bool = False,
) -> str:
    """
    Remove a document from SQLite, Chroma, and chunk FTS. Returns deleted doc id.
    """
    conn = connect(settings)
    doc = resolve_document(conn, identifier)
    if doc is None:
        conn.close()
        raise FileNotFoundError(f"No document matching: {identifier!r}")

    doc_id = doc.id
    _delete_vectors(collection, doc_id)
    delete_chunks_for_doc(conn, doc_id)
    delete_document_row(conn, doc_id)

    if remove_managed_copy:
        managed = settings.catalog_root / "files"
        try:
            p = Path(doc.path)
            if p.is_file() and managed in p.parents:
                p.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Could not remove managed copy %s: %s", doc.path, e)

    conn.close()
    return doc_id


def add_file(
    settings: Settings,
    collection: Collection,
    ollama: OllamaClient,
    path: Path,
    *,
    copy_into_library: bool = False,
    title: str | None = None,
    chunk_size: int = 1200,
    overlap: int = 200,
    pdf_ocr: str | None = None,
) -> IndexResult:
    """
    Extract text, record in SQLite, embed chunks. Returns IndexResult.
    Re-indexing the same stored path replaces prior vectors for that doc_id.
    Skips re-embed when content_hash is unchanged.
    """
    src = path.expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Not a file: {path}")

    ocr_mode = pdf_ocr if pdf_ocr is not None else settings.pdf_ocr_mode
    text, kind = extract_text(src, pdf_ocr=ocr_mode)
    if not text.strip():
        raise ExtractionError("Extracted text is empty.")

    chash = _content_hash(text)

    if copy_into_library:
        dest_dir = settings.catalog_root / "files"
        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = src.suffix.lower() or ""
        work_path = dest_dir / f"{chash}{suffix}"
        if not work_path.exists():
            shutil.copy2(src, work_path)
    else:
        work_path = src

    size_bytes = work_path.stat().st_size

    conn = connect(settings)
    existing = get_by_path(conn, str(work_path))
    doc_id = existing.id if existing else uuid.uuid4().hex

    if existing and existing.content_hash == chash:
        conn.close()
        log.debug("Skipping unchanged file %s", work_path)
        return IndexResult(doc_id=doc_id, chunk_count=existing.chunk_count, unchanged=True)

    if existing:
        _delete_vectors(collection, doc_id)
        delete_chunks_for_doc(conn, doc_id)

    display_title = title.strip() if title else None
    source_label = display_title if display_title else work_path.name

    extra = {"doc_id": doc_id, "kind": kind}
    if kind == "pdf-scanned":
        extra["ocr_used"] = "true"

    n, parts = ingest_string(
        collection,
        ollama,
        text,
        source_label=source_label,
        max_chars=chunk_size,
        overlap=overlap,
        extra_metadata=_meta_str(extra),
        return_chunks=True,
    )

    replace_chunks(conn, doc_id, parts)

    upsert_document(
        conn,
        doc_id,
        str(work_path),
        kind,
        display_title,
        chash,
        size_bytes,
        n,
    )
    conn.close()

    if n == 0:
        raise ExtractionError(
            "Nothing was indexed (no chunks). Try a larger file or lower chunk_size."
        )

    return IndexResult(doc_id=doc_id, chunk_count=n, unchanged=False)


def add_url(
    settings: Settings,
    collection: Collection,
    ollama: OllamaClient,
    url: str,
    *,
    title: str | None = None,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> IndexResult:
    """Fetch URL, extract article/PDF text, index with source URL metadata."""
    try:
        fc = fetch_and_extract(url, settings)
    except httpx.HTTPError as e:
        raise ExtractionError(f"Could not fetch URL: {e}") from e

    text = fc.text
    if not text.strip():
        raise ExtractionError("Empty content after extraction.")

    canonical = fc.canonical_url
    chash = _content_hash(text)
    size_bytes = len(text.encode("utf-8"))

    conn = connect(settings)
    existing = get_by_path(conn, canonical)
    doc_id = existing.id if existing else uuid.uuid4().hex

    if existing and existing.content_hash == chash:
        conn.close()
        return IndexResult(doc_id=doc_id, chunk_count=existing.chunk_count, unchanged=True)

    if existing:
        _delete_vectors(collection, doc_id)
        delete_chunks_for_doc(conn, doc_id)

    display_title = (title.strip() if title else None) or fc.title or canonical
    source_label = display_title

    extra = _meta_str(
        {
            "doc_id": doc_id,
            "kind": fc.kind,
            "source_url": canonical,
            "fetched_at": fc.fetched_at,
            "mime_type": fc.content_type,
        }
    )

    n, parts = ingest_string(
        collection,
        ollama,
        text,
        source_label=source_label,
        max_chars=chunk_size,
        overlap=overlap,
        extra_metadata=extra,
        return_chunks=True,
    )

    replace_chunks(conn, doc_id, parts)

    upsert_document(
        conn,
        doc_id,
        canonical,
        fc.kind,
        display_title,
        chash,
        size_bytes,
        n,
    )
    conn.close()

    if n == 0:
        raise ExtractionError("Nothing was indexed from URL.")

    return IndexResult(doc_id=doc_id, chunk_count=n, unchanged=False)
