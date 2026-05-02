"""Load plain text from supported file types (PDF, Markdown, plain text)."""

from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader


class ExtractionError(ValueError):
    pass


# Suffixes we can read without extra converters (keep in sync with extract_text)
SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {".pdf", ".md", ".markdown", ".mdown", ".txt", ".text", ".journal", ".entry"}
)


def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def list_ingestable_files(
    root: Path,
    *,
    recursive: bool = True,
    include_hidden: bool = False,
) -> list[Path]:
    """
    Paths under root that Cluny can ingest, sorted. Skips directories and
    unsupported extensions; when include_hidden is False, skips files under
    a path segment starting with '.' (e.g. .git, .venv).
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ExtractionError(f"Not a directory: {root}")

    candidates: list[Path]
    if recursive:
        candidates = [p for p in root.rglob("*") if p.is_file()]
    else:
        candidates = [p for p in root.iterdir() if p.is_file()]

    out: list[Path] = []
    for p in candidates:
        if not include_hidden:
            try:
                rel = p.relative_to(root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel.parts):
                continue
        if is_supported_file(p):
            out.append(p)
    return sorted(out)


def extract_text(path: Path, pdf_ocr: str = "auto") -> tuple[str, str]:
    """
    Return (text, kind). For PDFs, ``pdf_ocr`` is auto | always | never (see CLUNY_PDF_OCR).
    """
    if not path.is_file():
        raise ExtractionError(f"Not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path, pdf_ocr)
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


def _pdf_text_layer(path: Path) -> str:
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

    return "\n\n".join(parts).strip()


def _extract_pdf(path: Path, pdf_ocr: str) -> tuple[str, str]:
    mode = pdf_ocr.strip().lower()
    if mode not in ("auto", "always", "never"):
        mode = "auto"

    layer = _pdf_text_layer(path)

    if mode == "always":
        text = _pdf_ocr(path)
        if not text.strip():
            raise ExtractionError("OCR produced no text from PDF.")
        return text, "pdf-scanned"

    if layer:
        return layer, "pdf"

    if mode == "never":
        raise ExtractionError(
            "No text layer in PDF and CLUNY_PDF_OCR=never. "
            "For scanned PDFs set CLUNY_PDF_OCR=auto or install OCR dependencies."
        )

    text = _pdf_ocr(path)
    if not text.strip():
        raise ExtractionError(
            "OCR produced no text. Check that Tesseract is installed (e.g. brew install tesseract)."
        )
    return text, "pdf-scanned"


def _pdf_ocr(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise ExtractionError(
            "PDF OCR needs PyMuPDF, pytesseract, and Pillow. "
            "Install: pip install pymupdf pytesseract Pillow "
            "and the Tesseract engine (e.g. brew install tesseract)."
        ) from e

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        raise ExtractionError(f"Could not open PDF for OCR: {e}") from e

    parts: list[str] = []
    matrix = fitz.Matrix(2.0, 2.0)
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png = pix.tobytes("png")
            img = Image.open(io.BytesIO(png))
            chunk = pytesseract.image_to_string(img)
            if chunk.strip():
                parts.append(chunk.strip())
    finally:
        doc.close()

    return "\n\n".join(parts).strip()
