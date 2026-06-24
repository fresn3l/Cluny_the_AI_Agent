"""Main chat window: transcript, input, stats sidebar, background RAG."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QFont, QKeyEvent, QTextOption
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cluny.agent import run_agent
from cluny.config import Settings
from cluny.documents import add_file
from cluny.library_db import connect, document_count, get_tags_for_doc, list_documents
from cluny.ollama_client import OllamaError
from cluny.query import RagAnswer, RagSource, rag_answer, rag_answer_stream
from cluny.store import get_collection


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    token = Signal(str)
    sources = Signal(object)


class RagRunnable(QRunnable):
    """Runs RAG off the UI thread; streams tokens when not in agent mode."""

    def __init__(self, question: str, k: int, *, agent_mode: str) -> None:
        super().__init__()
        self._question = question
        self._k = k
        self._agent_mode = agent_mode
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            if self._agent_mode in ("knowledge", "tasks", "all"):
                result = run_agent(self._question, mode=self._agent_mode)  # type: ignore[arg-type]
                body = result.answer
                if result.tool_calls:
                    body = "Tools: " + "; ".join(result.tool_calls) + "\n\n" + body
                self.signals.finished.emit(
                    RagAnswer(answer=body, sources=(), empty_index=False)
                )
                return

            stream, sources, empty = rag_answer_stream(self._question, k=self._k)
            if empty:
                self.signals.finished.emit(
                    RagAnswer(
                        answer="".join(stream),
                        sources=(),
                        empty_index=True,
                    )
                )
                return

            self.signals.sources.emit(sources)
            for token in stream:
                self.signals.token.emit(token)
            self.signals.finished.emit(
                RagAnswer(answer="", sources=sources, empty_index=False)
            )
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(str(e))


class IngestRunnable(QRunnable):
    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        self._paths = paths
        self.signals = WorkerSignals()

    def run(self) -> None:
        settings = Settings.from_env()
        collection = get_collection(settings)
        from cluny.ollama_client import OllamaClient

        ollama = OllamaClient(settings)
        ok, fail = 0, 0
        for path in self._paths:
            try:
                add_file(settings, collection, ollama, path)
                ok += 1
            except Exception:  # noqa: BLE001
                fail += 1
        self.signals.finished.emit((ok, fail))


_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #ececec;
    font-size: 14px;
}
QScrollArea { border: none; background: transparent; }
#sidebar {
    background-color: #252526;
    border-right: 1px solid #3c3c3c;
}
#statsLabel {
    color: #a0a0a0;
    font-size: 12px;
}
QPushButton {
    background-color: #3a3a3a;
    border: 1px solid #555;
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 20px;
}
QPushButton:hover { background-color: #454545; }
QPushButton:pressed { background-color: #2d2d2d; }
QPushButton:disabled { color: #666; border-color: #444; }
#sendBtn {
    background-color: #2563eb;
    border: none;
    font-weight: 600;
    color: #fff;
}
#sendBtn:hover { background-color: #1d4ed8; }
#sendBtn:disabled { background-color: #374151; color: #9ca3af; }
QTextEdit#inputBox {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 12px;
    padding: 12px;
    selection-background-color: #2563eb;
}
QSpinBox {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 4px 8px;
}
QListWidget {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 6px;
}
#bubbleInner {
    background-color: #2d2d2d;
    border-radius: 16px;
    border: 1px solid #3f3f3f;
}
#userBubble #bubbleInner {
    background-color: #1e3a5f;
    border-color: #3b6fcd;
}
#bubbleText {
    background: transparent;
    color: #ececec;
}
QMenuBar {
    background-color: #252526;
    border-bottom: 1px solid #3c3c3c;
}
QMenuBar::item:selected { background: #3a3a3a; }
"""


class _Bubble(QFrame):
    """Single message block (user or assistant)."""

    def __init__(
        self,
        *,
        role: str,
        body: str,
        sources: tuple[RagSource, ...] = (),
        empty_notice: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("userBubble" if role == "user" else "assistantBubble")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 6)

        inner = QFrame()
        inner.setObjectName("bubbleInner")
        v = QVBoxLayout(inner)
        self._inner_layout = v
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFrameStyle(QFrame.Shape.NoFrame)
        self._text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._text.setPlainText(body)
        self._text.setObjectName("bubbleText")
        self._text.document().setDocumentMargin(0)
        self._text.setMinimumHeight(52)
        self._text.setMaximumHeight(420)

        font = QFont()
        font.setPointSize(13)
        self._text.setFont(font)

        v.addWidget(self._text)

        self._sources_widget: QTextEdit | None = None
        if sources and not empty_notice:
            src_header = QLabel("Sources")
            src_header.setObjectName("statsLabel")
            v.addWidget(src_header)
            lines = []
            for s in sources:
                lines.append(f"• {s.label}\n  {s.snippet}")
            src_body = QTextEdit()
            src_body.setReadOnly(True)
            src_body.setFrameStyle(QFrame.Shape.NoFrame)
            src_body.setPlainText("\n\n".join(lines))
            src_body.setMinimumHeight(72)
            src_body.setMaximumHeight(160)
            src_body.setObjectName("bubbleText")
            v.addWidget(src_body)
            self._sources_widget = src_body

        if role == "user":
            outer.addStretch(1)
            inner.setMaximumWidth(560)
            outer.addWidget(inner, 0, Qt.AlignmentFlag.AlignRight)
        else:
            inner.setMaximumWidth(720)
            outer.addWidget(inner, 0, Qt.AlignmentFlag.AlignLeft)
            outer.addStretch(1)

    def append_text(self, token: str) -> None:
        self._text.moveCursor(self._text.textCursor().MoveOperation.End)
        self._text.insertPlainText(token)

    def set_sources(self, sources: tuple[RagSource, ...]) -> None:
        if self._sources_widget is not None or not sources:
            return
        src_header = QLabel("Sources")
        src_header.setObjectName("statsLabel")
        self._inner_layout.addWidget(src_header)
        lines = [f"• {s.label}\n  {s.snippet}" for s in sources]
        src_body = QTextEdit()
        src_body.setReadOnly(True)
        src_body.setFrameStyle(QFrame.Shape.NoFrame)
        src_body.setPlainText("\n\n".join(lines))
        src_body.setMinimumHeight(72)
        src_body.setMaximumHeight(160)
        self._inner_layout.addWidget(src_body)
        self._sources_widget = src_body


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cluny")
        self.resize(1100, 760)
        self.setStyleSheet(_STYLESHEET)
        self.setAcceptDrops(True)

        self._busy = False
        self._thread_pool = QThreadPool.globalInstance()
        self._stream_bubble: _Bubble | None = None
        self._pending_sources: tuple[RagSource, ...] = ()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        sidebar = self._build_sidebar()
        splitter.addWidget(sidebar)

        chat_col = QWidget()
        chat_layout = QVBoxLayout(chat_col)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._transcript_inner = QWidget()
        self._messages_layout = QVBoxLayout(self._transcript_inner)
        self._messages_layout.setContentsMargins(16, 16, 16, 16)
        self._messages_layout.setSpacing(4)
        self._messages_layout.addStretch(1)

        self._scroll.setWidget(self._transcript_inner)
        chat_layout.addWidget(self._scroll, 1)

        input_row = self._build_input_row()
        chat_layout.addWidget(input_row)

        splitter.addWidget(chat_col)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 820])

        self._build_menu()
        self._append_assistant_welcome()
        self._refresh_stats()
        self._refresh_library()

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        add_a = QAction("&Add documents…", self)
        add_a.triggered.connect(self._add_documents)
        file_menu.addAction(add_a)
        file_menu.addSeparator()
        quit_a = QAction("&Quit", self)
        quit_a.setShortcut("Ctrl+Q")
        quit_a.triggered.connect(self.close)
        file_menu.addAction(quit_a)

        help_menu = bar.addMenu("&Help")
        about = QAction("&About Cluny", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Cluny",
            "<h3>Cluny</h3>"
            "<p>Local second brain — Ollama + Chroma. Your notes stay on disk.</p>"
            "<p>Ingest with <b>File → Add documents</b> or "
            "<code>cluny add</code>. Toggle <b>Agent mode</b> for tool-calling.</p>",
        )

    def _build_sidebar(self) -> QWidget:
        w = QWidget()
        w.setObjectName("sidebar")
        w.setMinimumWidth(240)
        w.setMaximumWidth(360)
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 20, 16, 16)
        v.setSpacing(12)

        title = QLabel("Cluny")
        tf = QFont()
        tf.setPointSize(18)
        tf.setWeight(QFont.Weight.DemiBold)
        title.setFont(tf)
        v.addWidget(title)

        self._stats_label = QLabel()
        self._stats_label.setObjectName("statsLabel")
        self._stats_label.setWordWrap(True)
        v.addWidget(self._stats_label)

        refresh = QPushButton("Refresh stats")
        refresh.clicked.connect(self._refresh_all)
        v.addWidget(refresh)

        v.addWidget(QLabel("Library"))
        self._doc_list = QListWidget()
        self._doc_list.setMaximumHeight(180)
        self._doc_list.itemClicked.connect(self._on_doc_clicked)
        v.addWidget(self._doc_list)

        v.addWidget(QLabel("Chunks to retrieve (k)"))
        self._k_spin = QSpinBox()
        self._k_spin.setRange(1, 25)
        self._k_spin.setValue(5)
        v.addWidget(self._k_spin)

        self._agent_combo = QComboBox()
        self._agent_combo.addItems(["Ask (RAG)", "Knowledge agent", "Tasks agent", "All tools"])
        v.addWidget(self._agent_combo)

        v.addStretch(1)

        data_hint = QLabel("Drop files here to ingest.\nData: CLUNY_DATA_DIR")
        data_hint.setObjectName("statsLabel")
        data_hint.setWordWrap(True)
        v.addWidget(data_hint)

        return w

    def _build_input_row(self) -> QWidget:
        wrap = QFrame()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(16, 8, 16, 16)

        self._input = QTextEdit()
        self._input.setObjectName("inputBox")
        self._input.setPlaceholderText(
            "Message Cluny…  (Enter to send, Shift+Enter for newline)"
        )
        self._input.setMinimumHeight(80)
        self._input.setMaximumHeight(200)
        self._input.installEventFilter(self)
        lay.addWidget(self._input)

        row = QHBoxLayout()
        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.clicked.connect(self._on_send)
        row.addStretch(1)
        row.addWidget(self._send_btn)
        lay.addLayout(row)
        return wrap

    def dragEnterEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: ANN001, N802
        paths = [
            Path(u.toLocalFile())
            for u in event.mimeData().urls()
            if u.isLocalFile()
        ]
        files = [p for p in paths if p.is_file()]
        if files:
            self._ingest_paths(files)
        event.acceptProposedAction()

    def _add_documents(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add documents to Cluny",
            "",
            "Documents (*.pdf *.md *.txt *.json *.journal);;All files (*)",
        )
        if paths:
            self._ingest_paths([Path(p) for p in paths])

    def _ingest_paths(self, paths: list[Path]) -> None:
        runnable = IngestRunnable(paths)
        runnable.signals.finished.connect(self._on_ingest_done)
        runnable.signals.error.connect(
            lambda m: QMessageBox.warning(self, "Ingest error", m)
        )
        self._thread_pool.start(runnable)

    @Slot(object)
    def _on_ingest_done(self, result: object) -> None:
        if isinstance(result, tuple) and len(result) == 2:
            ok, fail = result
            QMessageBox.information(
                self,
                "Ingest complete",
                f"Indexed {ok} file(s)" + (f", {fail} failed" if fail else ""),
            )
        self._refresh_all()

    def _on_doc_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            QMessageBox.information(self, "Document path", str(path))

    def eventFilter(self, obj: QObject, event: object) -> bool:
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                mods = event.modifiers()
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    return False
                self._on_send()
                return True
        return super().eventFilter(obj, event)

    def _append_assistant_welcome(self) -> None:
        text = (
            "Ask anything grounded in your indexed notes. "
            "Drop files on the sidebar or use File → Add documents. "
            "Use the mode dropdown for RAG vs knowledge/tasks agent."
        )
        self._insert_bubble(_Bubble(role="assistant", body=text))

    def _insert_bubble(self, bubble: QWidget) -> None:
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, bubble)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _append_user(self, text: str) -> None:
        self._insert_bubble(_Bubble(role="user", body=text.strip()))

    def _append_assistant_result(self, result: RagAnswer) -> None:
        if self._stream_bubble is not None and result.answer:
            self._stream_bubble.append_text(result.answer)
        elif result.answer or result.sources:
            bubble = _Bubble(
                role="assistant",
                body=result.answer.strip(),
                sources=result.sources,
                empty_notice=result.empty_index,
            )
            self._insert_bubble(bubble)

    def _append_error(self, message: str) -> None:
        self._insert_bubble(_Bubble(role="assistant", body=f"Error:\n\n{message}"))

    @Slot()
    def _on_send(self) -> None:
        if self._busy:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._busy = True
        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)
        self._stream_bubble = None
        self._pending_sources = ()

        self._append_user(text)
        self._input.clear()

        thinking = QLabel("Thinking…")
        thinking.setObjectName("statsLabel")
        thinking.setContentsMargins(24, 4, 16, 8)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, thinking)
        self._thinking_widget = thinking
        QTimer.singleShot(0, self._scroll_to_bottom)

        k = self._k_spin.value()
        mode_idx = self._agent_combo.currentIndex()
        if mode_idx == 0:
            agent_mode = "ask"
        elif mode_idx == 1:
            agent_mode = "knowledge"
        elif mode_idx == 2:
            agent_mode = "tasks"
        else:
            agent_mode = "all"
        runnable = RagRunnable(text, k, agent_mode=agent_mode)
        runnable.signals.finished.connect(self._on_rag_finished)
        runnable.signals.error.connect(self._on_rag_error)
        runnable.signals.token.connect(self._on_rag_token)
        runnable.signals.sources.connect(self._on_rag_sources)
        self._thread_pool.start(runnable)

    def _remove_thinking(self) -> None:
        if hasattr(self, "_thinking_widget") and self._thinking_widget is not None:
            self._messages_layout.removeWidget(self._thinking_widget)
            self._thinking_widget.deleteLater()
            self._thinking_widget = None

    @Slot(str)
    def _on_rag_token(self, token: str) -> None:
        self._remove_thinking()
        if self._stream_bubble is None:
            self._stream_bubble = _Bubble(role="assistant", body="")
            self._insert_bubble(self._stream_bubble)
        self._stream_bubble.append_text(token)
        QTimer.singleShot(0, self._scroll_to_bottom)

    @Slot(object)
    def _on_rag_sources(self, sources: object) -> None:
        if isinstance(sources, tuple):
            self._pending_sources = sources

    @Slot(object)
    def _on_rag_finished(self, result: object) -> None:
        self._remove_thinking()
        if isinstance(result, RagAnswer):
            if result.empty_index:
                self._append_assistant_result(result)
            elif self._stream_bubble is not None and self._pending_sources:
                self._stream_bubble.set_sources(self._pending_sources)
            elif not self._stream_bubble:
                self._append_assistant_result(result)
        self._stream_bubble = None
        self._busy = False
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._input.setFocus()
        QTimer.singleShot(0, self._scroll_to_bottom)

    @Slot(str)
    def _on_rag_error(self, message: str) -> None:
        self._remove_thinking()
        self._stream_bubble = None
        self._append_error(message)
        self._busy = False
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._input.setFocus()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _refresh_all(self) -> None:
        self._refresh_stats()
        self._refresh_library()

    def _refresh_library(self) -> None:
        try:
            settings = Settings.from_env()
            conn = connect(settings)
            rows = list_documents(conn)
            self._doc_list.clear()
            for d in rows:
                tags = get_tags_for_doc(conn, d.id)
                tag_s = f" [{', '.join(tags)}]" if tags else ""
                label = f"{(d.title or d.path)[:40]}{tag_s}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, d.path)
                item.setToolTip(d.path)
                self._doc_list.addItem(item)
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_stats(self) -> None:
        try:
            settings = Settings.from_env()
            collection = get_collection(settings)
            n_chunks = collection.count()
            conn = connect(settings)
            n_docs = document_count(conn)
            conn.close()
            self._stats_label.setText(
                f"Vector chunks: <b>{n_chunks}</b><br/>"
                f"Catalog documents: <b>{n_docs}</b><br/><br/>"
                f"Chat model: <code>{settings.chat_model}</code><br/>"
                f"Embed model: <code>{settings.embed_model}</code>"
            )
        except OllamaError as e:
            self._stats_label.setText(f"Could not load stats:\n{e}")
        except Exception as e:  # noqa: BLE001
            self._stats_label.setText(f"Could not load stats:\n{e}")
