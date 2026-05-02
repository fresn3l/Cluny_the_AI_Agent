"""Fetch URLs and extract article text (HTML) or PDF bytes."""

from __future__ import annotations

import io
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import trafilatura

try:
    from trafilatura import extract_metadata
except ImportError:
    from trafilatura.metadata import extract_metadata

from cluny.config import Settings
from cluny.extract import ExtractionError, extract_text
from cluny.url_rules import UrlRules, host_from_url


@dataclass(frozen=True)
class FetchedContent:
    text: str
    title: str | None
    canonical_url: str
    kind: str  # web-html | web-pdf
    content_type: str
    fetched_at: str  # ISO8601


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    if not p.scheme:
        url = "https://" + url
    return url


def _build_url_rules(settings: Settings) -> UrlRules:
    return UrlRules(
        mode=settings.url_mode,
        allow_hosts=settings.url_allow_hosts,
        block_hosts=settings.url_block_hosts,
    )


def fetch_and_extract(url: str, settings: Settings) -> FetchedContent:
    """
    Download a URL, apply host rules, return main text (HTML article or PDF text).
    """
    rules = _build_url_rules(settings)
    url = _normalize_url(url)
    rules.check(url)

    headers = {"User-Agent": settings.url_user_agent}
    timeout = httpx.Timeout(settings.url_timeout_sec)
    max_b = settings.url_max_bytes

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            total = 0
            chunks: list[bytes] = []
            for part in r.iter_bytes():
                total += len(part)
                if total > max_b:
                    raise ExtractionError(
                        f"Response larger than CLUNY_URL_MAX_BYTES ({max_b}): {url}"
                    )
                chunks.append(part)
            body = b"".join(chunks)
            ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            final_url = str(r.url)

    fetched_at = _now_iso()

    if ctype == "application/pdf" or body[:4] == b"%PDF":
        return _extract_pdf_bytes(body, final_url, settings, fetched_at, ctype or "application/pdf")

    if ctype in ("text/html", "application/xhtml+xml") or b"<html" in body[:5000].lower():
        return _extract_html(body, final_url, fetched_at, ctype or "text/html")

    # Plain text / markdown-ish
    if ctype.startswith("text/"):
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception as e:
            raise ExtractionError(f"Could not decode text response: {e}") from e
        if not text.strip():
            raise ExtractionError("Empty text response from URL")
        return FetchedContent(
            text=text.strip(),
            title=host_from_url(final_url),
            canonical_url=final_url,
            kind="web-html",
            content_type=ctype,
            fetched_at=fetched_at,
        )

    raise ExtractionError(
        f"Unsupported Content-Type {ctype!r} for {final_url}. "
        f"Use HTML, PDF, or text/* URLs."
    )


def _extract_html(
    body: bytes,
    final_url: str,
    fetched_at: str,
    ctype: str,
) -> FetchedContent:
    downloaded = body.decode("utf-8", errors="replace")
    meta = extract_metadata(downloaded, url=final_url)
    text = trafilatura.extract(
        downloaded,
        url=final_url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not text or not text.strip():
        raise ExtractionError(
            "Could not extract article text from HTML (trafilatura). "
            "The page may require JavaScript or be blocked."
        )
    title = meta.title if meta and meta.title else None
    return FetchedContent(
        text=text.strip(),
        title=title.strip() if title else None,
        canonical_url=final_url,
        kind="web-html",
        content_type=ctype,
        fetched_at=fetched_at,
    )


def _extract_pdf_bytes(
    body: bytes,
    final_url: str,
    settings: Settings,
    fetched_at: str,
    ctype: str,
) -> FetchedContent:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(body)
        path = Path(tmp.name)
    try:
        text, _kind = extract_text(path, pdf_ocr=settings.pdf_ocr_mode)
    finally:
        path.unlink(missing_ok=True)

    title = Path(urlparse(final_url).path).name or host_from_url(final_url)
    return FetchedContent(
        text=text,
        title=title if title else None,
        canonical_url=final_url,
        kind="web-pdf",
        content_type=ctype,
        fetched_at=fetched_at,
    )

