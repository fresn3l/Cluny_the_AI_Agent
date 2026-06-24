"""Watch a directory and re-ingest journal files when they change."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from cluny.config import Settings
from cluny.documents import add_file, delete_document
from cluny.extract import ExtractionError, list_ingestable_files, is_supported_file
from cluny.library_db import connect, get_by_path
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.store import get_collection

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

log = logging.getLogger(__name__)


def run_initial_sync(
    root: Path,
    settings: Settings,
    collection: "Collection",
    ollama: OllamaClient,
    *,
    include_hidden: bool = False,
    chunk_size: int = 1200,
    overlap: int = 200,
    pdf_ocr: str | None = None,
) -> tuple[int, int]:
    """
    Ingest all supported files under root. Returns (ok_count, fail_count).
    """
    try:
        files = list_ingestable_files(
            root, recursive=True, include_hidden=include_hidden
        )
    except ExtractionError:
        return 0, 0

    ok, fail = 0, 0
    for path in files:
        try:
            result = add_file(
                settings,
                collection,
                ollama,
                path,
                copy_into_library=False,
                title=_title_for_watched_path(root, path),
                chunk_size=chunk_size,
                overlap=overlap,
                pdf_ocr=pdf_ocr,
            )
            ok += 1
            if result.unchanged:
                log.debug("unchanged %s", path)
        except (OllamaError, ExtractionError, FileNotFoundError) as e:
            fail += 1
            log.warning("[watch] skip %s: %s", path, e)
    return ok, fail


def _title_for_watched_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


class _Debounce:
    def __init__(self, delay_sec: float, callback: Callable[[set[Path]], None]) -> None:
        self.delay_sec = delay_sec
        self.callback = callback
        self._lock = threading.Lock()
        self._pending: set[Path] = set()
        self._timer: threading.Timer | None = None

    def schedule(self, path: Path) -> None:
        with self._lock:
            self._pending.add(path)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay_sec, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            batch = self._pending
            self._pending = set()
            self._timer = None
        if batch:
            self.callback(batch)

    def flush(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            batch = self._pending
            self._pending = set()
        if batch:
            self.callback(batch)


def watch_directory(
    root: Path,
    settings: Settings,
    *,
    debounce_sec: float = 1.5,
    chunk_size: int = 1200,
    overlap: int = 200,
    pdf_ocr: str | None = None,
    include_hidden: bool = False,
    on_event_log: Callable[[str], None] | None = None,
) -> None:
    """
    Block until KeyboardInterrupt. Uses watchdog if installed.
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as e:
        raise RuntimeError(
            "Install the watchdog package: pip install watchdog"
        ) from e

    collection = get_collection(settings)
    ollama = OllamaClient(settings)
    ingest_lock = threading.Lock()

    def log_msg(msg: str) -> None:
        if on_event_log:
            on_event_log(msg)
        else:
            log.info(msg)

    def ingest_one(path: Path) -> None:
        if not path.is_file() or not is_supported_file(path):
            return
        with ingest_lock:
            try:
                result = add_file(
                    settings,
                    collection,
                    ollama,
                    path,
                    copy_into_library=False,
                    title=_title_for_watched_path(root, path),
                    chunk_size=chunk_size,
                    overlap=overlap,
                    pdf_ocr=pdf_ocr,
                )
                if result.unchanged:
                    log_msg(f"[watch] unchanged {path}")
                else:
                    log_msg(f"[watch] indexed {path}")
            except (OllamaError, ExtractionError, FileNotFoundError) as e:
                log_msg(f"[watch] skip {path}: {e}")

    def remove_one(path: Path) -> None:
        resolved = str(path.resolve())
        with ingest_lock:
            conn = connect(settings)
            doc = get_by_path(conn, resolved)
            conn.close()
            if doc is None:
                return
            try:
                delete_document(settings, collection, doc.id)
                log_msg(f"[watch] removed {path}")
            except FileNotFoundError:
                pass

    def ingest_batch(paths: set[Path]) -> None:
        for path in sorted(paths):
            ingest_one(path)

    debounce = _Debounce(debounce_sec, ingest_batch)

    class Handler(FileSystemEventHandler):
        def on_created(self, event):  # noqa: ANN001
            if event.is_directory:
                return
            debounce.schedule(Path(event.src_path))

        def on_modified(self, event):  # noqa: ANN001
            if event.is_directory:
                return
            debounce.schedule(Path(event.src_path))

        def on_moved(self, event):  # noqa: ANN001
            if getattr(event, "is_directory", False):
                return
            debounce.schedule(Path(event.dest_path))

        def on_deleted(self, event):  # noqa: ANN001
            if event.is_directory:
                return
            remove_one(Path(event.src_path))

    ok, fail = run_initial_sync(
        root,
        settings,
        collection,
        ollama,
        include_hidden=include_hidden,
        chunk_size=chunk_size,
        overlap=overlap,
        pdf_ocr=pdf_ocr,
    )
    log_msg(f"[watch] initial sync: {ok} file(s) indexed, {fail} failed/skipped")

    observer = Observer()
    observer.schedule(Handler(), str(root), recursive=True)
    observer.start()
    log_msg(f"[watch] watching {root} (recursive). Ctrl+C to stop.")

    try:
        while observer.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        log_msg("[watch] stopping…")
    finally:
        debounce.flush()
        observer.stop()
        observer.join(timeout=5.0)
