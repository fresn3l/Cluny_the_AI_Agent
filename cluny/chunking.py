"""Split long text into overlapping chunks for embedding."""

from __future__ import annotations


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """
    Character-based chunks with overlap so sentences split across boundaries
    still appear in at least one chunk.
    """
    text = text.strip()
    if not text:
        return []

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be in [0, max_chars)")

    chunks: list[str] = []
    start = 0
    n = len(text)
    step = max_chars - overlap

    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start += step

    return chunks
