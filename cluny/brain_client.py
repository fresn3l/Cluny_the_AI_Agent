"""Optional HTTP client for widget/GUI when CLUNY_BRAIN_URL is set."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from cluny.config import Settings
from cluny.kosistenz_context import KosistenzContext
from cluny.supervisor import SourceCitation, SupervisorResult


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

    def _headers(self, *, accept_sse: bool = False) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if accept_sse:
            h["Accept"] = "text/event-stream"
        if self.token:
            h["X-Cluny-Token"] = self.token
        return h

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()

    def _chat_payload(
        self,
        question: str,
        *,
        context: str | None = None,
        context_json: KosistenzContext | dict | None = None,
        session_id: str | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"question": question}
        if context:
            payload["context"] = context
        if context_json is not None:
            if isinstance(context_json, KosistenzContext):
                payload["context_json"] = context_json.model_dump(exclude_none=True)
            else:
                payload["context_json"] = context_json
        if session_id:
            payload["session_id"] = session_id
        if collection:
            payload["collection"] = collection
        return payload

    def _parse_chat_response(self, data: dict[str, Any]) -> SupervisorResult:
        sources = tuple(
            SourceCitation(
                label=str(s.get("label", "")),
                snippet=str(s.get("snippet", "")),
                doc_path=s.get("doc_path"),
                chunk_index=s.get("chunk_index"),
            )
            for s in data.get("sources") or []
        )
        return SupervisorResult(
            route=data.get("route", "ask"),  # type: ignore[arg-type]
            answer=str(data.get("answer", "")),
            tool_calls=list(data.get("tool_calls") or []),
            sources=sources,
        )

    def chat(
        self,
        question: str,
        *,
        context: str | None = None,
        context_json: KosistenzContext | dict | None = None,
        session_id: str | None = None,
        collection: str | None = None,
    ) -> tuple[SupervisorResult, str]:
        """Returns (result, session_id)."""
        payload = self._chat_payload(
            question,
            context=context,
            context_json=context_json,
            session_id=session_id,
            collection=collection,
        )
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.base_url}/chat",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        sid = str(data.get("session_id", session_id or ""))
        return self._parse_chat_response(data), sid

    def chat_stream(
        self,
        question: str,
        *,
        context: str | None = None,
        context_json: KosistenzContext | dict | None = None,
        session_id: str | None = None,
        collection: str | None = None,
    ) -> Iterator[dict[str, Any] | str]:
        """Yield parsed SSE payloads: meta dict, sources dict, token dict, then '[DONE]'."""
        payload = self._chat_payload(
            question,
            context=context,
            context_json=context_json,
            session_id=session_id,
            collection=collection,
        )
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat/stream",
                json=payload,
                headers=self._headers(accept_sse=True),
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        yield "[DONE]"
                        return
                    yield json.loads(chunk)

    def propose(
        self,
        question: str,
        *,
        context: str | None = None,
        context_json: KosistenzContext | dict | None = None,
        collection: str | None = None,
        k: int = 5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        payload: dict[str, Any] = {"question": question, "k": k}
        if context:
            payload["context"] = context
        if context_json is not None:
            if isinstance(context_json, KosistenzContext):
                payload["context_json"] = context_json.model_dump(exclude_none=True)
            else:
                payload["context_json"] = context_json
        if collection:
            payload["collection"] = collection
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{self.base_url}/propose",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return list(data.get("proposals") or []), list(data.get("sources") or [])

    def brain_config_get(self) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.base_url}/brain/config", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def brain_config_put(
        self,
        *,
        global_persona: str | None = None,
        prompts: dict[str, str | None] | None = None,
        behavior: dict[str, str | int | None] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if global_persona is not None:
            payload["global_persona"] = global_persona
        if prompts is not None:
            payload["prompts"] = prompts
        if behavior is not None:
            payload["behavior"] = behavior
        with httpx.Client(timeout=30.0) as client:
            r = client.put(
                f"{self.base_url}/brain/config",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    def brain_config_reset(
        self,
        *,
        prompt_key: str | None = None,
        reset_behavior: bool = False,
        reset_persona: bool = False,
        reset_all: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "prompt_key": prompt_key,
            "reset_behavior": reset_behavior,
            "reset_persona": reset_persona,
            "reset_all": reset_all,
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{self.base_url}/brain/config/reset",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    def ingest_text(
        self,
        text: str,
        *,
        source: str = "widget-capture",
        title: str | None = None,
        collection: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "catalog": True,
            "source": source,
        }
        if title:
            payload["title"] = title
        if collection:
            payload["collection"] = collection
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
    context_json: KosistenzContext | dict | None = None,
    session_id: str | None = None,
    collection: str | None = None,
) -> SupervisorResult:
    """Route chat through HTTP when CLUNY_BRAIN_URL is set, else in-process."""
    settings = settings or Settings.load()
    client = BrainClient.from_settings(settings)
    if client is not None:
        result, _sid = client.chat(
            question,
            context=context,
            context_json=context_json,
            session_id=session_id,
            collection=collection,
        )
        return result
    from cluny.chat_service import api_chat

    data = api_chat(
        question,
        settings=settings,
        context=context,
        context_json=context_json,
        session_id=session_id,
        collection=collection,
    )
    sources = tuple(
        SourceCitation(
            label=str(s["label"]),
            snippet=str(s["snippet"]),
            doc_path=s.get("doc_path"),
            chunk_index=s.get("chunk_index"),
        )
        for s in data.get("sources") or []
    )
    return SupervisorResult(
        route=data["route"],  # type: ignore[arg-type]
        answer=data["answer"],
        tool_calls=list(data.get("tool_calls") or []),
        sources=sources,
    )


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
