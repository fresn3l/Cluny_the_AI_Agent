"""Environment-backed settings (no secrets required for local Ollama)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v.strip() if v else default


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    chat_model: str
    embed_model: str
    data_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        data = Path(_get("CLUNY_DATA_DIR", ".cluny")).expanduser().resolve()
        return cls(
            ollama_base_url=_get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            chat_model=_get("OLLAMA_CHAT_MODEL", "llama3.2"),
            embed_model=_get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            data_dir=data,
        )
