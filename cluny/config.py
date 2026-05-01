"""Environment-backed settings (no secrets required for local Ollama)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v.strip() if v else default


def find_repo_root() -> Path | None:
    """
    Directory that contains this project's pyproject.toml.

    Walks up from the current working directory first (so running from a
    subfolder still finds the repo), then from the installed package path.
    """
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for parent in [start, *start.parents]:
            if (parent / "pyproject.toml").is_file():
                return parent
    return None


def _resolve_data_dir(raw: str) -> Path:
    """Absolute paths stay absolute; relative CLUNY_DATA_DIR is anchored to the repo root when known."""
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    root = find_repo_root()
    base = root if root is not None else Path.cwd()
    return (base / p).resolve()


def load_dotenv_if_present() -> None:
    """Load `.env` from the repo root when present; otherwise fall back to cwd."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    candidates: list[Path] = []
    root = find_repo_root()
    if root is not None:
        candidates.append(root / ".env")
    candidates.append(Path.cwd() / ".env")
    for env in candidates:
        if env.is_file():
            load_dotenv(env)
            return


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    chat_model: str
    embed_model: str
    data_dir: Path

    @classmethod
    def from_env(cls) -> Settings:
        data = _resolve_data_dir(_get("CLUNY_DATA_DIR", ".cluny"))
        return cls(
            ollama_base_url=_get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            chat_model=_get("OLLAMA_CHAT_MODEL", "llama3.2"),
            embed_model=_get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            data_dir=data,
        )
