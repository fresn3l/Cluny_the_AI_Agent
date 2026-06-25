"""Environment-backed settings (no secrets required for local Ollama)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
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
    supervisor_mode: str
    api_bind_host: str
    api_port: int
    api_token: str
    backup_dir: Path

    @property
    def catalog_root(self) -> Path:
        """Directory under data_dir that holds the SQLite DB and managed file copies."""
        return self.data_dir / self.catalog_dir_name

    def with_user_overlay(self) -> "Settings":
        """Merge user_config.json overrides (models, k, hybrid weight)."""
        from cluny.user_config import load_user_config

        uc = load_user_config(self)
        return replace(
            self,
            chat_model=uc.chat_model or self.chat_model,
            embed_model=uc.embed_model or self.embed_model,
            retrieval_k=max(1, uc.retrieval_k) if uc.retrieval_k else self.retrieval_k,
            hybrid_vector_weight=uc.hybrid_vector_weight,
        )

    @classmethod
    def load(cls) -> "Settings":
        """Env settings with user_config.json overlay applied."""
        return cls.from_env().with_user_overlay()

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

        rerank = _get("CLUNY_RERANK", "off").lower()
        if rerank not in ("off", "llm", "cross"):
            rerank = "off"

        sup = _get("CLUNY_SUPERVISOR", "llm").lower()
        if sup not in ("llm", "regex"):
            sup = "llm"

        raw_backup = _get("CLUNY_BACKUP_DIR", "backups")
        backup_p = Path(raw_backup).expanduser()
        if not backup_p.is_absolute():
            backup_p = (data / backup_p).resolve()

        api_token = _get("CLUNY_API_TOKEN", "")

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
            rerank_mode=rerank,
            chunk_pdf_size=max(400, _int("CLUNY_CHUNK_PDF_SIZE", 1500)),
            chunk_pdf_overlap=max(0, _int("CLUNY_CHUNK_PDF_OVERLAP", 250)),
            chunk_md_size=max(400, _int("CLUNY_CHUNK_MD_SIZE", 1200)),
            chunk_md_overlap=max(0, _int("CLUNY_CHUNK_MD_OVERLAP", 200)),
            chunk_journal_size=max(400, _int("CLUNY_CHUNK_JOURNAL_SIZE", 800)),
            chunk_journal_overlap=max(0, _int("CLUNY_CHUNK_JOURNAL_OVERLAP", 100)),
            chunk_default_size=max(400, _int("CLUNY_CHUNK_DEFAULT_SIZE", 1200)),
            chunk_default_overlap=max(0, _int("CLUNY_CHUNK_DEFAULT_OVERLAP", 200)),
            supervisor_mode=sup,
            api_bind_host=_get("CLUNY_API_BIND", "127.0.0.1"),
            api_port=max(1, _int("CLUNY_API_PORT", 8787)),
            api_token=api_token,
            backup_dir=backup_p,
        )
