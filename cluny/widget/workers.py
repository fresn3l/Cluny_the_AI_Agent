"""Background workers for the menu bar widget."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from cluny.brain_client import BrainClient, chat_brain, ingest_text_brain
from cluny.brain_service import fetch_brain_health
from cluny.config import Settings
from cluny.library_db import connect, list_collections
from cluny.tasks_db import connect as tasks_connect, create_task
from cluny.widget.glance import build_glance_summary, format_glance_text


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    token = Signal(str)
    sources = Signal(object)


class ChatStreamWorker(QRunnable):
    """Stream chat via HTTP brain (/chat/stream) or in-process fallback."""

    def __init__(
        self,
        question: str,
        *,
        collection: str | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__()
        self._question = question
        self._collection = collection
        self._session_id = session_id
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            client = BrainClient.from_settings(settings)
            if client is not None:
                parts: list[str] = []
                route = "ask"
                for event in client.chat_stream(
                    self._question,
                    collection=self._collection or None,
                    session_id=self._session_id,
                ):
                    if event == "[DONE]":
                        break
                    if not isinstance(event, dict):
                        continue
                    if "token" in event:
                        tok = str(event["token"])
                        parts.append(tok)
                        self.signals.token.emit(tok)
                    if "sources" in event:
                        self.signals.sources.emit(event["sources"])
                    if "route" in event:
                        route = str(event["route"])
                    if "session_id" in event:
                        self._session_id = str(event["session_id"])
                body = "".join(parts)
                if route != "ask":
                    body = f"[route: {route}]\n\n{body}"
                self.signals.finished.emit(
                    {"answer": body, "session_id": self._session_id}
                )
                return

            result = chat_brain(
                self._question,
                settings=settings,
                collection=self._collection or None,
                session_id=self._session_id,
            )
            body = result.answer
            if result.tool_calls:
                body = "Tools: " + "; ".join(result.tool_calls) + "\n\n" + body
            text = f"[route: {result.route}]\n\n{body}"
            self.signals.finished.emit({"answer": text, "session_id": self._session_id})
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class ProposeWorker(QRunnable):
    def __init__(
        self,
        question: str,
        *,
        context: str | None = None,
        collection: str | None = None,
    ) -> None:
        super().__init__()
        self._question = question
        self._context = context
        self._collection = collection
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            client = BrainClient.from_settings(settings)
            if client is None:
                self.signals.error.emit("Brain HTTP client not configured (set CLUNY_BRAIN_URL).")
                return
            proposals = client.propose(
                self._question,
                context=self._context,
                collection=self._collection,
            )
            lines: list[str] = []
            for p in proposals:
                title = p.get("title", "")
                est = p.get("estimate_minutes")
                due = p.get("due")
                extra = []
                if est:
                    extra.append(f"{est} min")
                if due:
                    extra.append(f"due {due}")
                suffix = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"• {title}{suffix}")
            self.signals.finished.emit("\n".join(lines) if lines else "No proposals.")
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class CaptureWorker(QRunnable):
    def __init__(self, text: str, *, source: str = "widget-capture") -> None:
        super().__init__()
        self._text = text
        self._source = source
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            count, unchanged = ingest_text_brain(
                self._text,
                settings=settings,
                source=self._source,
            )
            msg = f"Indexed {count} chunk(s)."
            if unchanged:
                msg = "Unchanged (already indexed)."
            self.signals.finished.emit(msg)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class TaskWorker(QRunnable):
    def __init__(self, title: str, due_at: str | None) -> None:
        super().__init__()
        self._title = title
        self._due_at = due_at
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            conn = tasks_connect(settings)
            task = create_task(conn, self._title, due_at=self._due_at)
            conn.close()
            due = f" (due {task.due_at})" if task.due_at else ""
            self.signals.finished.emit(f"Created: {task.title}{due}")
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class GlanceWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            summary = build_glance_summary(settings)
            self.signals.finished.emit(format_glance_text(summary))
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class BrainHealthWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            health = fetch_brain_health()
            if not health.ok:
                self.signals.finished.emit("Brain: offline")
            elif not health.brain_ready:
                msg = health.message or "Ollama not ready"
                self.signals.finished.emit(f"Brain: {msg}")
            else:
                self.signals.finished.emit("Brain: ready")
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class CollectionsWorker(QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            conn = connect(settings)
            names = list_collections(conn)
            conn.close()
            self.signals.finished.emit(names)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))
