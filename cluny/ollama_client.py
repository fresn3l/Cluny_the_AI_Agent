"""HTTP client for a local Ollama server (chat + embeddings)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx

from cluny.config import Settings


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, settings: Settings, timeout: float | None = None) -> None:
        self._base = settings.ollama_base_url
        self._chat_model = settings.chat_model
        self._embed_model = settings.embed_model
        self._timeout = timeout if timeout is not None else settings.ollama_timeout_sec
        self._retries = settings.ollama_retries

    def embed(self, text: str) -> list[float]:
        batch = self.embed_batch([text])
        return batch[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts; uses Ollama /api/embed when available."""
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self._embed_model, "input": texts}
        try:
            data = self._post_json("/api/embed", payload)
            embeddings = data.get("embeddings")
            if isinstance(embeddings, list) and len(embeddings) == len(texts):
                return [[float(x) for x in e] for e in embeddings]
        except OllamaError:
            pass
        # Fallback for older Ollama: single /api/embeddings per text
        out: list[list[float]] = []
        for text in texts:
            data = self._post_json("/api/embeddings", {"model": self._embed_model, "prompt": text})
            emb = data.get("embedding")
            if not isinstance(emb, list):
                raise OllamaError(f"unexpected embeddings response: {data!r}")
            out.append([float(x) for x in emb])
        return out

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

    def chat_stream(self, system: str, user: str) -> Iterator[str]:
        """Yield content tokens as they arrive from Ollama."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload: dict[str, Any] = {
            "model": self._chat_model,
            "messages": messages,
            "stream": True,
        }
        url = f"{self._base}/api/chat"
        last_err: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    with client.stream("POST", url, json=payload) as r:
                        if r.status_code >= 400:
                            raise OllamaError(f"/api/chat failed {r.status_code}: {r.read().decode()}")
                        for line in r.iter_lines():
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            msg = data.get("message") or {}
                            content = msg.get("content")
                            if isinstance(content, str) and content:
                                yield content
                            if data.get("done"):
                                return
                return
            except (httpx.HTTPError, OllamaError) as e:
                last_err = e
                if attempt < self._retries:
                    time.sleep(0.5 * (attempt + 1))
        raise OllamaError(str(last_err)) from last_err

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Single chat turn with tool definitions; returns raw Ollama response."""
        payload: dict[str, Any] = {
            "model": self._chat_model,
            "messages": messages,
            "tools": tools,
            "stream": False,
        }
        return self._post_json("/api/chat", payload)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}{path}"
        last_err: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    r = client.post(url, json=payload)
                if r.status_code >= 400:
                    raise OllamaError(f"{path} failed {r.status_code}: {r.text}")
                data = r.json()
                if not isinstance(data, dict):
                    raise OllamaError(f"{path} returned non-object JSON")
                return data
            except (httpx.HTTPError, OllamaError) as e:
                last_err = e
                if attempt < self._retries:
                    time.sleep(0.5 * (attempt + 1))
        raise OllamaError(str(last_err)) from last_err
