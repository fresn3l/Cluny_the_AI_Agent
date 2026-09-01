"""Compact popover panel: Ask, Capture, Propose/Task, Glance."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QThreadPool, Slot
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
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

from cluny.config import Settings
from cluny.user_config import UserConfig, load_user_config, save_user_config
from cluny.widget.styles import WIDGET_STYLESHEET
from cluny.widget.workers import (
    BrainHealthWorker,
    CaptureWorker,
    ChatStreamWorker,
    CollectionsWorker,
    GlanceWorker,
    ProposeWorker,
    TaskWorker,
)


class WidgetPanel(QFrame):
    """Frameless popover shown from the menu bar tray."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("widgetPanel")
        self.setFixedSize(420, 560)
        self.setStyleSheet(WIDGET_STYLESHEET)

        self._thread_pool = QThreadPool.globalInstance()
        self._busy = False
        self._settings = Settings.load()
        self._user_config = load_user_config(self._settings)
        self._session_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        header = QLabel("Cluny")
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        header_row.addWidget(header)
        header_row.addStretch(1)
        self._brain_label = QLabel("")
        self._brain_label.setObjectName("statusLabel")
        header_row.addWidget(self._brain_label)
        root.addLayout(header_row)

        coll_row = QHBoxLayout()
        coll_row.addWidget(QLabel("Collection"))
        self._collection_combo = QComboBox()
        self._collection_combo.addItem("(all)", "")
        self._collection_combo.currentIndexChanged.connect(self._on_collection_changed)
        coll_row.addWidget(self._collection_combo, 1)
        root.addLayout(coll_row)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        self._tabs.addTab(self._build_ask_tab(), "Ask")
        self._tabs.addTab(self._build_capture_tab(), "Capture")
        if self._user_config.standalone_mode:
            self._tabs.addTab(self._build_task_tab(), "Task")
        else:
            self._tabs.addTab(self._build_propose_tab(), "Propose")
        self._tabs.addTab(self._build_glance_tab(), "Glance")

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._refresh_brain_status()
        self._load_collections()

    def show_and_focus(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._tabs.setCurrentIndex(0)
        self._ask_input.setFocus()
        self._refresh_brain_status()
        self._load_collections()

    def _current_collection(self) -> str | None:
        data = self._collection_combo.currentData()
        if data:
            return str(data)
        return None

    def _on_collection_changed(self) -> None:
        coll = self._current_collection() or ""
        self._user_config.ask_collection = coll
        save_user_config(self._settings, self._user_config)

    def _build_ask_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._ask_input = QTextEdit()
        self._ask_input.setPlaceholderText("Ask Cluny anything…")
        self._ask_input.setMaximumHeight(80)
        self._ask_input.installEventFilter(self)
        lay.addWidget(self._ask_input)

        self._ask_btn = QPushButton("Ask")
        self._ask_btn.setObjectName("primaryBtn")
        self._ask_btn.clicked.connect(self._on_ask)
        lay.addWidget(self._ask_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._ask_answer = QTextEdit()
        self._ask_answer.setReadOnly(True)
        self._ask_answer.setPlaceholderText("Answers stream here…")
        self._ask_answer.setMinimumHeight(200)
        lay.addWidget(self._ask_answer, 1)

        self._sources_label = QLabel("")
        self._sources_label.setObjectName("statusLabel")
        self._sources_label.setWordWrap(True)
        lay.addWidget(self._sources_label)
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

    def _build_propose_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._propose_input = QTextEdit()
        self._propose_input.setPlaceholderText(
            "What should I work on? Cluny suggests items for Kosistenz to schedule."
        )
        self._propose_input.setMaximumHeight(80)
        lay.addWidget(self._propose_input)

        self._propose_btn = QPushButton("Suggest work")
        self._propose_btn.setObjectName("primaryBtn")
        self._propose_btn.clicked.connect(self._on_propose)
        lay.addWidget(self._propose_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._propose_result = QLabel("Proposals appear here.")
        self._propose_result.setWordWrap(True)
        self._propose_result.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._propose_result, 1)
        return w

    def _build_task_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self._task_title = QLineEdit()
        self._task_title.setPlaceholderText("Task title (standalone mode)")
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
        if hasattr(self, "_task_btn"):
            self._task_btn.setEnabled(not busy)
        if hasattr(self, "_propose_btn"):
            self._propose_btn.setEnabled(not busy)

    def _refresh_brain_status(self) -> None:
        worker = BrainHealthWorker()
        worker.signals.finished.connect(lambda t: self._brain_label.setText(str(t)))
        worker.signals.error.connect(lambda e: self._brain_label.setText(f"Brain: {e}"))
        self._thread_pool.start(worker)

    def _load_collections(self) -> None:
        worker = CollectionsWorker()
        worker.signals.finished.connect(self._on_collections_loaded)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_collections_loaded(self, names: object) -> None:
        if not isinstance(names, list):
            return
        current = self._user_config.ask_collection or ""
        self._collection_combo.blockSignals(True)
        self._collection_combo.clear()
        self._collection_combo.addItem("(all)", "")
        for name in names:
            self._collection_combo.addItem(str(name), str(name))
        idx = self._collection_combo.findData(current)
        self._collection_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._collection_combo.blockSignals(False)

    def _on_ask(self) -> None:
        if self._busy:
            return
        text = self._ask_input.toPlainText().strip()
        if not text:
            return
        self._set_busy(True)
        self._status.setText("Thinking…")
        self._ask_answer.clear()
        self._sources_label.clear()
        worker = ChatStreamWorker(
            text,
            collection=self._current_collection(),
            session_id=self._session_id,
        )
        worker.signals.token.connect(self._on_ask_token)
        worker.signals.sources.connect(self._on_ask_sources)
        worker.signals.finished.connect(self._on_ask_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    @Slot(str)
    def _on_ask_token(self, token: str) -> None:
        self._ask_answer.moveCursor(QTextCursor.MoveOperation.End)
        self._ask_answer.insertPlainText(token)

    @Slot(object)
    def _on_ask_sources(self, sources: object) -> None:
        if not isinstance(sources, list):
            return
        labels = [str(s.get("label", "")) for s in sources if isinstance(s, dict)]
        if labels:
            self._sources_label.setText("Sources: " + ", ".join(labels))

    @Slot(object)
    def _on_ask_done(self, payload: object) -> None:
        if isinstance(payload, dict) and payload.get("session_id"):
            self._session_id = str(payload["session_id"])
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

    def _on_propose(self) -> None:
        if self._busy:
            return
        text = self._propose_input.toPlainText().strip()
        if not text:
            return
        self._set_busy(True)
        self._status.setText("Suggesting…")
        worker = ProposeWorker(text, collection=self._current_collection())
        worker.signals.finished.connect(self._on_propose_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    @Slot(object)
    def _on_propose_done(self, text: object) -> None:
        self._propose_result.setText(str(text))
        self._status.setText("")
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
