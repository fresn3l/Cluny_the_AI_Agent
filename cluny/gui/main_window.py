"""Main chat window: transcript, input, stats sidebar, background RAG."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QEvent, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QFont, QKeyEvent, QTextOption
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
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
from cluny.brain_client import BrainClient, chat_brain
from cluny.config import Settings
from cluny.documents import add_file
from cluny.gui.brain_editor import (
    export_brain_config_dialog,
    import_brain_config_dialog,
    open_brain_editor,
)
from cluny.library_db import (
    connect,
    document_count,
    get_collections_for_doc,
    get_tags_for_doc,
    list_collections,
    list_documents,
)
from cluny.ollama_client import OllamaError
from cluny.query import RagAnswer, RagSource, rag_answer_stream
from cluny.sessions import add_message, connect as sessions_connect, get_or_create_last_session, list_messages
from cluny.store import get_collection
from cluny.user_config import UserConfig, load_user_config, save_user_config


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    token = Signal(str)
    sources = Signal(object)


class RagRunnable(QRunnable):
    """Runs RAG off the UI thread; streams tokens when not in agent mode."""

    def __init__(
        self,
        question: str,
        k: int,
        *,
        agent_mode: str,
        collection_name: str | None = None,
    ) -> None:
        super().__init__()
        self._question = question
        self._k = k
        self._agent_mode = agent_mode
        self._collection_name = collection_name
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            client = BrainClient.from_settings(settings)
            if client is not None:
                self._run_http(client)
                return

            if self._agent_mode == "chat":
                result = chat_brain(
                    self._question,
                    settings=settings,
                    collection=self._collection_name,
                )
                body = result.answer
                if result.tool_calls:
                    body = "Tools: " + "; ".join(result.tool_calls) + "\n\n" + body
                body = f"[route: {result.route}]\n\n{body}"
                self.signals.finished.emit(
                    RagAnswer(answer=body, sources=(), empty_index=False)
                )
                return

            if self._agent_mode in ("knowledge", "tasks", "all", "planner"):
                result = run_agent(
                    self._question,
                    mode=self._agent_mode,  # type: ignore[arg-type]
                    settings=settings,
                )
                body = result.answer
                if result.tool_calls:
                    body = "Tools: " + "; ".join(result.tool_calls) + "\n\n" + body
                self.signals.finished.emit(
                    RagAnswer(answer=body, sources=(), empty_index=False)
                )
                return

            stream, sources, empty = rag_answer_stream(
                self._question,
                k=self._k,
                settings=settings,
                collection_name=self._collection_name,
            )
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

    def _run_http(self, client: BrainClient) -> None:
        """Stream via /chat/stream when CLUNY_BRAIN_URL is set (packaged app mode)."""
        parts: list[str] = []
        sources: tuple[RagSource, ...] = ()
        route = self._agent_mode
        for event in client.chat_stream(
            self._question,
            collection=self._collection_name,
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
                raw_sources = event["sources"]
                if isinstance(raw_sources, list):
                    sources = tuple(
                        RagSource(
                            label=str(s.get("label", "")),
                            snippet=str(s.get("snippet", "")),
                            doc_path=s.get("doc_path"),
                            chunk_index=s.get("chunk_index"),
                        )
                        for s in raw_sources
                    )
                    self.signals.sources.emit(sources)
            if "route" in event:
                route = str(event["route"])

        body = "".join(parts)
        if route != "ask":
            body = f"[route: {route}]\n\n{body}"
        self.signals.finished.emit(
            RagAnswer(answer=body, sources=sources, empty_index=False)
        )


class IngestRunnable(QRunnable):
    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        self._paths = paths
        self.signals = WorkerSignals()

    def run(self) -> None:
        settings = Settings.load()
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

        self._sources_widget: QListWidget | None = None
        if sources and not empty_notice:
            src_header = QLabel("Sources (click to open)")
            src_header.setObjectName("statsLabel")
            v.addWidget(src_header)
            src_list = QListWidget()
            src_list.setMaximumHeight(120)
            for s in sources:
                item = QListWidgetItem(f"{s.label}\n{s.snippet[:120]}…" if len(s.snippet) > 120 else f"{s.label}\n{s.snippet}")
                item.setData(Qt.ItemDataRole.UserRole, (s.doc_path, s.chunk_index, s.snippet))
                src_list.addItem(item)
            src_list.itemClicked.connect(self._on_source_clicked)
            v.addWidget(src_list)
            self._sources_widget = src_list

        if role == "user":
            outer.addStretch(1)
            inner.setMaximumWidth(560)
            outer.addWidget(inner, 0, Qt.AlignmentFlag.AlignRight)
        else:
            inner.setMaximumWidth(720)
            outer.addWidget(inner, 0, Qt.AlignmentFlag.AlignLeft)
            outer.addStretch(1)

    def _on_source_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        path, _chunk_idx, snippet = data
        if path and Path(path).is_file():
            if sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                QMessageBox.information(self, "Source file", path)
        else:
            QMessageBox.information(self, "Source excerpt", snippet or item.text())

    def append_text(self, token: str) -> None:
        self._text.moveCursor(self._text.textCursor().MoveOperation.End)
        self._text.insertPlainText(token)

    def set_sources(self, sources: tuple[RagSource, ...]) -> None:
        if self._sources_widget is not None or not sources:
            return
        src_header = QLabel("Sources (click to open)")
        src_header.setObjectName("statsLabel")
        self._inner_layout.addWidget(src_header)
        src_list = QListWidget()
        src_list.setMaximumHeight(120)
        for s in sources:
            item = QListWidgetItem(f"{s.label}")
            item.setData(Qt.ItemDataRole.UserRole, (s.doc_path, s.chunk_index, s.snippet))
            src_list.addItem(item)
        src_list.itemClicked.connect(self._on_source_clicked)
        self._inner_layout.addWidget(src_list)
        self._sources_widget = src_list


class _SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None, config: UserConfig) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cluny settings")
        self._config = config
        form = QFormLayout(self)
        self._k_spin = QSpinBox()
        self._k_spin.setRange(1, 25)
        self._k_spin.setValue(config.retrieval_k)
        form.addRow("Retrieval k", self._k_spin)
        self._hybrid = QDoubleSpinBox()
        self._hybrid.setRange(0.0, 1.0)
        self._hybrid.setSingleStep(0.1)
        self._hybrid.setValue(config.hybrid_vector_weight)
        form.addRow("Vector weight (hybrid)", self._hybrid)
        self._chat = QTextEdit()
        self._chat.setPlainText(config.chat_model)
        self._chat.setMaximumHeight(36)
        form.addRow("Chat model", self._chat)
        self._embed = QTextEdit()
        self._embed.setPlainText(config.embed_model)
        self._embed.setMaximumHeight(36)
        form.addRow("Embed model", self._embed)
        self._standalone = QCheckBox("Standalone mode (menu bar shows Task tab instead of Propose)")
        self._standalone.setChecked(config.standalone_mode)
        form.addRow(self._standalone)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_config(self) -> UserConfig:
        return UserConfig(
            chat_model=self._chat.toPlainText().strip() or self._config.chat_model,
            embed_model=self._embed.toPlainText().strip() or self._config.embed_model,
            retrieval_k=self._k_spin.value(),
            hybrid_vector_weight=self._hybrid.value(),
            agent_mode=self._config.agent_mode,
            ask_collection=self._config.ask_collection,
            standalone_mode=self._standalone.isChecked(),
            first_run_complete=self._config.first_run_complete,
        )


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
        self._settings = Settings.load()
        self._user_config = load_user_config(self._settings)
        self._sess_conn = sessions_connect(self._settings)
        self._session_id = get_or_create_last_session(self._sess_conn)

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
        self._restore_transcript()
        self._refresh_stats()
        self._refresh_library()
        self._k_spin.setValue(self._user_config.retrieval_k)
        idx = {"ask": 0, "chat": 1, "knowledge": 2, "tasks": 3, "all": 4, "planner": 5}.get(
            self._user_config.agent_mode, 0
        )
        self._agent_combo.setCurrentIndex(idx)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        if hasattr(self, "_sess_conn") and self._sess_conn:
            self._sess_conn.close()
        super().closeEvent(event)

    def _restore_transcript(self) -> None:
        msgs = list_messages(self._sess_conn, self._session_id)
        if not msgs:
            self._append_assistant_welcome()
            return
        for m in msgs:
            if m.role == "user":
                self._insert_bubble(_Bubble(role="user", body=m.content))
            elif m.role == "assistant":
                self._insert_bubble(_Bubble(role="assistant", body=m.content))

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        add_a = QAction("&Add documents…", self)
        add_a.triggered.connect(self._add_documents)
        file_menu.addAction(add_a)
        file_menu.addSeparator()
        settings_a = QAction("&Settings…", self)
        settings_a.triggered.connect(self._open_settings)
        file_menu.addAction(settings_a)
        file_menu.addSeparator()
        quit_a = QAction("&Quit", self)
        quit_a.setShortcut("Ctrl+Q")
        quit_a.triggered.connect(self.close)
        file_menu.addAction(quit_a)

        brain_menu = bar.addMenu("&Brain")
        edit_brain = QAction("&Edit instructions…", self)
        edit_brain.triggered.connect(self._open_brain_editor)
        brain_menu.addAction(edit_brain)
        export_brain = QAction("&Export brain config…", self)
        export_brain.triggered.connect(self._export_brain_config)
        brain_menu.addAction(export_brain)
        import_brain = QAction("&Import brain config…", self)
        import_brain.triggered.connect(self._import_brain_config)
        brain_menu.addAction(import_brain)

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
        self._k_spin.setValue(self._user_config.retrieval_k)
        v.addWidget(self._k_spin)

        v.addWidget(QLabel("Collection (Ask / Chat RAG)"))
        self._collection_combo = QComboBox()
        self._collection_combo.addItem("(all collections)", "")
        v.addWidget(self._collection_combo)

        self._agent_combo = QComboBox()
        self._agent_combo.addItems(
            [
                "Ask (RAG)",
                "Chat (auto)",
                "Knowledge agent",
                "Tasks agent",
                "All tools",
                "Planner",
            ]
        )
        v.addWidget(self._agent_combo)

        v.addStretch(1)

        data_hint = QLabel("Drop files here to ingest.\nData: CLUNY_DATA_DIR")
        data_hint.setObjectName("statsLabel")
        data_hint.setWordWrap(True)
        v.addWidget(data_hint)

        return w

    def _open_settings(self) -> None:
        dlg = _SettingsDialog(self, self._user_config)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._user_config = dlg.result_config()
            save_user_config(self._settings, self._user_config)
            self._k_spin.setValue(self._user_config.retrieval_k)
            QMessageBox.information(
                self,
                "Settings saved",
                "Settings apply to the next message. "
                "Restart the menu bar widget for standalone mode tab changes.",
            )

    def _open_brain_editor(self) -> None:
        if open_brain_editor(self):
            self._user_config = load_user_config(self._settings)
            self._k_spin.setValue(self._user_config.retrieval_k)
            QMessageBox.information(
                self,
                "Brain config saved",
                "Instruction changes apply to the next message.",
            )

    def _export_brain_config(self) -> None:
        export_brain_config_dialog(self)

    def _import_brain_config(self) -> None:
        if import_brain_config_dialog(self):
            self._user_config = load_user_config(self._settings)
            self._k_spin.setValue(self._user_config.retrieval_k)

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
        add_message(self._sess_conn, self._session_id, "user", text)

        thinking = QLabel("Thinking…")
        thinking.setObjectName("statsLabel")
        thinking.setContentsMargins(24, 4, 16, 8)
        idx = self._messages_layout.count() - 1
        self._messages_layout.insertWidget(idx, thinking)
        self._thinking_widget = thinking
        QTimer.singleShot(0, self._scroll_to_bottom)

        k = self._k_spin.value()
        mode_idx = self._agent_combo.currentIndex()
        mode_map = {
            0: "ask",
            1: "chat",
            2: "knowledge",
            3: "tasks",
            4: "all",
            5: "planner",
        }
        agent_mode = mode_map.get(mode_idx, "ask")
        collection = self._collection_combo.currentData()
        collection_name = str(collection) if collection else None
        if collection_name == "":
            collection_name = None
        self._user_config.ask_collection = collection_name or ""
        save_user_config(self._settings, self._user_config)
        runnable = RagRunnable(
            text,
            k,
            agent_mode=agent_mode,
            collection_name=collection_name,
        )
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
                add_message(self._sess_conn, self._session_id, "assistant", result.answer)
            elif self._stream_bubble is not None:
                if self._pending_sources:
                    self._stream_bubble.set_sources(self._pending_sources)
                body = self._stream_bubble._text.toPlainText() if self._stream_bubble else ""
                if body:
                    add_message(self._sess_conn, self._session_id, "assistant", body)
            elif not self._stream_bubble:
                self._append_assistant_result(result)
                add_message(self._sess_conn, self._session_id, "assistant", result.answer)
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
        self._refresh_collections()

    def _refresh_collections(self) -> None:
        try:
            settings = Settings.load()
            conn = connect(settings)
            names = list_collections(conn)
            conn.close()
            current = self._user_config.ask_collection or ""
            self._collection_combo.blockSignals(True)
            self._collection_combo.clear()
            self._collection_combo.addItem("(all collections)", "")
            for name in names:
                self._collection_combo.addItem(name, name)
            idx = self._collection_combo.findData(current)
            self._collection_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._collection_combo.blockSignals(False)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_library(self) -> None:
        try:
            settings = Settings.load()
            conn = connect(settings)
            rows = list_documents(conn)
            self._doc_list.clear()
            for d in rows:
                tags = get_tags_for_doc(conn, d.id)
                colls = get_collections_for_doc(conn, d.id)
                tag_s = f" [{', '.join(tags)}]" if tags else ""
                coll_s = f" <{', '.join(colls)}>" if colls else ""
                label = f"{(d.title or d.path)[:36]}{tag_s}{coll_s}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, d.path)
                item.setToolTip(d.path)
                self._doc_list.addItem(item)
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_stats(self) -> None:
        try:
            settings = Settings.load()
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
