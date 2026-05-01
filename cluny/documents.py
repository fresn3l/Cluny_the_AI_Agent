"""Register files in the library DB and index them into Chroma."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from chromadb.api.models.Collection import Collection

from cluny.config import Settings
from cluny.extract import ExtractionError, extract_text
from cluny.ingest import ingest_string
from cluny.library_db import connect, get_by_path, upsert_document
from cluny.ollama_client import OllamaClient


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
) -> tuple[str, int]:
    """
    Extract text, record in SQLite, embed chunks. Returns (doc_id, chunk_count).
    Re-indexing the same stored path replaces prior vectors for that doc_id.
    """
    src = path.expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Not a file: {path}")

    text, kind = extract_text(src)
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

    if existing:
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass

    display_title = title.strip() if title else None
    source_label = display_title if display_title else work_path.name

    extra = {"doc_id": doc_id, "kind": kind}

    n = ingest_string(
        collection,
        ollama,
        text,
        source_label=source_label,
        max_chars=chunk_size,
        overlap=overlap,
        extra_metadata=extra,
    )

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

    return doc_id, n
