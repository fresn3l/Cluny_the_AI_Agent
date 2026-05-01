"""Load plain text from supported file types (PDF, Markdown, plain text)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


class ExtractionError(ValueError):
    pass


def extract_text(path: Path) -> tuple[str, str]:
    """
    Return (text, kind) where kind is one of: pdf, markdown, text, journal.
    """
    if not path.is_file():
        raise ExtractionError(f"Not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_text(path), "pdf"
    if suffix in {".md", ".markdown", ".mdown"}:
        return path.read_text(encoding="utf-8", errors="replace"), "markdown"
    if suffix in {".txt", ".text"}:
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    if suffix in {".journal", ".entry"}:
        return path.read_text(encoding="utf-8", errors="replace"), "journal"

    raise ExtractionError(
        f"Unsupported extension {suffix!r}. "
        f"Use .pdf, .md, .txt, or .journal (or add conversion yourself)."
    )


def _pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise ExtractionError(f"Could not open PDF: {e}") from e

    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text()
        except Exception as e:
            raise ExtractionError(f"Failed to read page {i + 1}: {e}") from e
        if t:
            parts.append(t)

    text = "\n\n".join(parts).strip()
    if not text:
        raise ExtractionError(
            "No text extracted from PDF. Scanned pages need OCR (not built into Cluny yet)."
        )
    return text
