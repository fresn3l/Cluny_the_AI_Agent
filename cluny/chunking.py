"""Split long text into overlapping chunks for embedding."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH = re.compile(r"\n\s*\n+")


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """
    Sentence-aware chunks with overlap so boundaries fall on natural breaks when possible.
    """
    text = text.strip()
    if not text:
        return []

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be in [0, max_chars)")

    units = _split_units(text)
    if not units:
        return _char_chunks(text, max_chars, overlap)

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        unit_len = len(unit)
        sep = 1 if current else 0
        if current and current_len + sep + unit_len > max_chars:
            chunk = _join_units(current)
            if chunk:
                chunks.append(chunk)
            current, current_len = _overlap_tail(current, overlap, max_chars)
            if current and current_len + sep + unit_len > max_chars:
                for sub in _char_chunks(unit, max_chars, overlap):
                    if sub:
                        chunks.append(sub)
                current = []
                current_len = 0
                continue
        if unit_len > max_chars:
            if current:
                chunk = _join_units(current)
                if chunk:
                    chunks.append(chunk)
                current = []
                current_len = 0
            chunks.extend(_char_chunks(unit, max_chars, overlap))
            continue
        if current:
            current_len += sep
        current.append(unit)
        current_len += unit_len

    if current:
        chunk = _join_units(current)
        if chunk:
            chunks.append(chunk)

    return chunks


def _split_units(text: str) -> list[str]:
    """Paragraphs first, then sentences within long paragraphs."""
    units: list[str] = []
    for para in _PARAGRAPH.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= 400:
            units.append(para)
        else:
            units.extend(s for s in _SENTENCE_END.split(para) if s.strip())
    return units


def _join_units(parts: list[str]) -> str:
    return "\n\n".join(parts).strip()


def _overlap_tail(parts: list[str], overlap: int, max_chars: int) -> tuple[list[str], int]:
    if overlap <= 0 or not parts:
        return [], 0
    tail: list[str] = []
    total = 0
    for unit in reversed(parts):
        extra = 2 if tail else 0
        if total + extra + len(unit) > overlap:
            break
        tail.insert(0, unit)
        total += extra + len(unit)
    if not tail and parts:
        last = parts[-1]
        if len(last) > overlap:
            tail = [last[-overlap:]]
            total = overlap
        else:
            tail = [last]
            total = len(last)
    return tail, min(total, max_chars)


def _char_chunks(text: str, max_chars: int, overlap: int) -> list[str]:
    """Fallback character-based chunking."""
    chunks: list[str] = []
    start = 0
    n = len(text)
    step = max_chars - overlap

    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            break_at = text.rfind(" ", start + max_chars // 2, end)
            if break_at > start:
                end = break_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1) if overlap else end
        if step > 0 and overlap == 0:
            start = end

    return chunks
