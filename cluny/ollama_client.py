"""HTTP client for a local Ollama server (chat + embeddings)."""

from __future__ import annotations

from typing import Any

import httpx

from cluny.config import Settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings, timeout: float = 120.0) -> None:
        self._base = settings.ollama_base_url
        self._chat_model = settings.chat_model
        self._embed_model = settings.embed_model
        self._timeout = timeout

    def embed(self, text: str) -> list[float]:
        payload: dict[str, Any] = {"model": self._embed_model, "prompt": text}
        data = self._post_json("/api/embeddings", payload)
        emb = data.get("embedding")
        if not isinstance(emb, list):
            raise OllamaError(f"unexpected embeddings response: {data!r}")
        return [float(x) for x in emb]

    def chat(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload: dict[str, Any] = {
            "model": self._chat_model,
            "messages": messages,
            "stream": False,
        }
        data = self._post_json("/api/chat", payload)
        msg = data.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str):
            raise OllamaError(f"unexpected chat response: {data!r}")
        return content

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload)
        if r.status_code >= 400:
            raise OllamaError(f"{path} failed {r.status_code}: {r.text}")
        data = r.json()
        if not isinstance(data, dict):
            raise OllamaError(f"{path} returned non-object JSON")
        return data
