"""Compact popover panel: Ask, Capture, Task, Glance."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QThreadPool, Slot
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cluny.widget.styles import WIDGET_STYLESHEET
from cluny.widget.workers import CaptureWorker, ChatWorker, GlanceWorker, TaskWorker


class WidgetPanel(QFrame):
    """Frameless popover shown from the menu bar tray."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("widgetPanel")
        self.setFixedSize(420, 520)
        self.setStyleSheet(WIDGET_STYLESHEET)

        self._thread_pool = QThreadPool.globalInstance()
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QLabel("Cluny")
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(header)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        self._tabs.addTab(self._build_ask_tab(), "Ask")
        self._tabs.addTab(self._build_capture_tab(), "Capture")
        self._tabs.addTab(self._build_task_tab(), "Task")
        self._tabs.addTab(self._build_glance_tab(), "Glance")

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

    def show_and_focus(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._tabs.setCurrentIndex(0)
        self._ask_input.setFocus()

    def _build_ask_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._ask_input = QTextEdit()
        self._ask_input.setPlaceholderText("Ask Cluny anything… (Chat auto-routes)")
        self._ask_input.setMaximumHeight(80)
        self._ask_input.installEventFilter(self)
        lay.addWidget(self._ask_input)

        self._ask_btn = QPushButton("Ask")
        self._ask_btn.setObjectName("primaryBtn")
        self._ask_btn.clicked.connect(self._on_ask)
        lay.addWidget(self._ask_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._ask_answer = QLabel("Answers appear here.")
        self._ask_answer.setObjectName("answerLabel")
        self._ask_answer.setWordWrap(True)
        self._ask_answer.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._ask_answer.setMinimumHeight(220)
        lay.addWidget(self._ask_answer, 1)
        return w

    def _build_capture_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._capture_input = QTextEdit()
        self._capture_input.setPlaceholderText("Paste text to save to your brain…")
        lay.addWidget(self._capture_input, 1)

        self._capture_btn = QPushButton("Save to brain")
        self._capture_btn.setObjectName("primaryBtn")
        self._capture_btn.clicked.connect(self._on_capture)
        lay.addWidget(self._capture_btn, 0, Qt.AlignmentFlag.AlignRight)
        return w

    def _build_task_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._task_title = QLineEdit()
        self._task_title.setPlaceholderText("Task title")
        lay.addWidget(self._task_title)

        self._task_due = QLineEdit()
        self._task_due.setPlaceholderText("Due (optional): tomorrow, +3d, ISO date")
        lay.addWidget(self._task_due)

        self._task_btn = QPushButton("Add task")
        self._task_btn.setObjectName("primaryBtn")
        self._task_btn.clicked.connect(self._on_task)
        lay.addWidget(self._task_btn, 0, Qt.AlignmentFlag.AlignRight)
        lay.addStretch(1)
        return w

    def _build_glance_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._on_glance_refresh)
        lay.addWidget(refresh, 0, Qt.AlignmentFlag.AlignRight)

        self._glance_text = QLabel("Tap Refresh to load stats.")
        self._glance_text.setWordWrap(True)
        self._glance_text.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._glance_text, 1)
        return w

    def eventFilter(self, obj: object, event: object) -> bool:
        if obj is self._ask_input and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False
                self._on_ask()
                return True
        return super().eventFilter(obj, event)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._ask_btn.setEnabled(not busy)
        self._capture_btn.setEnabled(not busy)
        self._task_btn.setEnabled(not busy)

    def _on_ask(self) -> None:
        if self._busy:
            return
        text = self._ask_input.toPlainText().strip()
        if not text:
            return
        self._set_busy(True)
        self._status.setText("Thinking…")
        self._ask_answer.setText("")
        worker = ChatWorker(text)
        worker.signals.finished.connect(self._on_ask_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_ask_done(self, answer: object) -> None:
        self._ask_answer.setText(str(answer))
        self._status.setText("")
        self._set_busy(False)

    def _on_capture(self) -> None:
        if self._busy:
            return
        text = self._capture_input.toPlainText().strip()
        if not text:
            return
        self._set_busy(True)
        self._status.setText("Indexing…")
        worker = CaptureWorker(text)
        worker.signals.finished.connect(self._on_capture_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_capture_done(self, msg: object) -> None:
        self._capture_input.clear()
        self._status.setText(str(msg))
        self._set_busy(False)

    def _on_task(self) -> None:
        if self._busy:
            return
        title = self._task_title.text().strip()
        if not title:
            return
        due = self._task_due.text().strip() or None
        self._set_busy(True)
        self._status.setText("Saving task…")
        worker = TaskWorker(title, due)
        worker.signals.finished.connect(self._on_task_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_task_done(self, msg: object) -> None:
        self._task_title.clear()
        self._task_due.clear()
        self._status.setText(str(msg))
        self._set_busy(False)

    def _on_glance_refresh(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._status.setText("Loading…")
        worker = GlanceWorker()
        worker.signals.finished.connect(self._on_glance_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_glance_done(self, text: object) -> None:
        self._glance_text.setText(str(text))
        self._status.setText("")
        self._set_busy(False)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._status.setText(f"Error: {message}")
        self._set_busy(False)
