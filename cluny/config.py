"""Environment-backed settings (no secrets required for local Ollama)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v.strip() if v else default


def _int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))
    except ValueError:
        return default


def _host_set(key: str) -> frozenset[str]:
    return frozenset(x.strip().lower() for x in _get(key, "").split(",") if x.strip())


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
    catalog_dir_name: str
    library_sqlite_name: str
    pdf_ocr_mode: str
    url_mode: str
    url_allow_hosts: frozenset[str]
    url_block_hosts: frozenset[str]
    url_max_bytes: int
    url_timeout_sec: float
    url_user_agent: str
    hybrid_vector_weight: float
    retrieval_k: int
    ollama_timeout_sec: float
    ollama_retries: int
    embed_batch_size: int
    rerank_mode: str
    chunk_pdf_size: int
    chunk_pdf_overlap: int
    chunk_md_size: int
    chunk_md_overlap: int
    chunk_journal_size: int
    chunk_journal_overlap: int
    chunk_default_size: int
    chunk_default_overlap: int

    @property
    def catalog_root(self) -> Path:
        """Directory under data_dir that holds the SQLite DB and managed file copies."""
        return self.data_dir / self.catalog_dir_name

    @classmethod
    def from_env(cls) -> Settings:
        data = _resolve_data_dir(_get("CLUNY_DATA_DIR", ".cluny"))
        raw_cat = _get("CLUNY_CATALOG_DIR", "library")
        catalog_dir_name = Path(raw_cat).name or "library"
        raw_name = _get("CLUNY_LIBRARY_SQLITE", "library.sqlite")
        # basename only so env cannot escape CLUNY_DATA_DIR/<catalog>/
        safe_name = Path(raw_name).name or "library.sqlite"

        ocr = _get("CLUNY_PDF_OCR", "auto").lower()
        if ocr not in ("auto", "always", "never"):
            ocr = "auto"

        url_mode = _get("CLUNY_URL_MODE", "open").lower()
        if url_mode not in ("open", "restricted"):
            url_mode = "open"

        return cls(
            ollama_base_url=_get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            chat_model=_get("OLLAMA_CHAT_MODEL", "llama3.2"),
            embed_model=_get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            data_dir=data,
            catalog_dir_name=catalog_dir_name,
            library_sqlite_name=safe_name,
            pdf_ocr_mode=ocr,
            url_mode=url_mode,
            url_allow_hosts=_host_set("CLUNY_URL_ALLOWLIST"),
            url_block_hosts=_host_set("CLUNY_URL_BLOCKLIST"),
            url_max_bytes=max(1_000_000, _int("CLUNY_URL_MAX_BYTES", 15_000_000)),
            url_timeout_sec=max(5.0, _float("CLUNY_URL_TIMEOUT_SEC", 30.0)),
            url_user_agent=_get(
                "CLUNY_URL_USER_AGENT",
                "Cluny/0.1 (+local second brain; respectful crawling)",
            ),
            hybrid_vector_weight=max(0.0, min(1.0, _float("CLUNY_HYBRID_VECTOR_WEIGHT", 0.5))),
            retrieval_k=max(1, _int("CLUNY_RETRIEVAL_K", 20)),
            ollama_timeout_sec=max(10.0, _float("OLLAMA_TIMEOUT_SEC", 120.0)),
            ollama_retries=max(0, _int("OLLAMA_RETRIES", 2)),
            embed_batch_size=max(1, _int("CLUNY_EMBED_BATCH_SIZE", 8)),
            rerank_mode=_get("CLUNY_RERANK", "off").lower()
            if _get("CLUNY_RERANK", "off").lower() in ("off", "llm")
            else "off",
            chunk_pdf_size=max(400, _int("CLUNY_CHUNK_PDF_SIZE", 1500)),
            chunk_pdf_overlap=max(0, _int("CLUNY_CHUNK_PDF_OVERLAP", 250)),
            chunk_md_size=max(400, _int("CLUNY_CHUNK_MD_SIZE", 1200)),
            chunk_md_overlap=max(0, _int("CLUNY_CHUNK_MD_OVERLAP", 200)),
            chunk_journal_size=max(400, _int("CLUNY_CHUNK_JOURNAL_SIZE", 800)),
            chunk_journal_overlap=max(0, _int("CLUNY_CHUNK_JOURNAL_OVERLAP", 100)),
            chunk_default_size=max(400, _int("CLUNY_CHUNK_DEFAULT_SIZE", 1200)),
            chunk_default_overlap=max(0, _int("CLUNY_CHUNK_DEFAULT_OVERLAP", 200)),
        )
