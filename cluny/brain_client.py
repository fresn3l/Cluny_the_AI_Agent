"""Optional HTTP client for widget/GUI when CLUNY_BRAIN_URL is set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from cluny.config import Settings
from cluny.supervisor import SupervisorResult


@dataclass(frozen=True)
class BrainClient:
    base_url: str
    token: str = ""

    @classmethod
    def from_settings(cls, settings: Settings) -> BrainClient | None:
        raw = settings.brain_url
        if not raw:
            return None
        return cls(base_url=raw.rstrip("/"), token=settings.api_token)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["X-Cluny-Token"] = self.token
        return h

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()

    def chat(self, question: str, *, context: str | None = None) -> SupervisorResult:
        payload: dict[str, Any] = {"question": question}
        if context:
            payload["context"] = context
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.base_url}/chat",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return SupervisorResult(
            route=data.get("route", "ask"),  # type: ignore[arg-type]
            answer=str(data.get("answer", "")),
            tool_calls=list(data.get("tool_calls") or []),
        )

    def ingest_text(
        self,
        text: str,
        *,
        source: str = "widget-capture",
        title: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "catalog": True,
            "source": source,
        }
        if title:
            payload["title"] = title
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.base_url}/ingest/text",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()


def chat_brain(
    question: str,
    *,
    settings: Settings | None = None,
    context: str | None = None,
) -> SupervisorResult:
    """Route chat through HTTP when CLUNY_BRAIN_URL is set, else in-process."""
    settings = settings or Settings.load()
    client = BrainClient.from_settings(settings)
    if client is not None:
        return client.chat(question, context=context)
    from cluny.supervisor import run_chat

    return run_chat(question, settings=settings, context=context)


def ingest_text_brain(
    text: str,
    *,
    settings: Settings | None = None,
    source: str = "widget-capture",
    title: str | None = None,
) -> tuple[int, bool]:
    """Index text via HTTP or in-process. Returns (chunk_count, unchanged)."""
    settings = settings or Settings.load()
    client = BrainClient.from_settings(settings)
    if client is not None:
        data = client.ingest_text(text, source=source, title=title)
        return int(data.get("chunk_count", 0)), False

    from cluny.documents import add_inline_text
    from cluny.ollama_client import OllamaClient
    from cluny.store import get_collection

    collection = get_collection(settings)
    ollama = OllamaClient(settings)
    result = add_inline_text(
        settings,
        collection,
        ollama,
        text,
        source_label=source,
        title=title,
    )
    return result.chunk_count, result.unchanged
