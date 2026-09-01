"""Background workers for the menu bar widget."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from cluny.brain_client import chat_brain, ingest_text_brain
from cluny.config import Settings
from cluny.tasks_db import connect as tasks_connect, create_task
from cluny.widget.glance import build_glance_summary, format_glance_text


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class ChatWorker(QRunnable):
    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            result = chat_brain(self._question, settings=settings)
            body = result.answer
            if result.tool_calls:
                body = "Tools: " + "; ".join(result.tool_calls) + "\n\n" + body
            text = f"[route: {result.route}]\n\n{body}"
            self.signals.finished.emit(text)
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
