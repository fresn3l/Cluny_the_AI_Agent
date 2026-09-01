"""Brain Editor dialog — edit Cluny instructions, behavior, and models."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cluny.brain_config import (
    DEFAULT_PROMPTS,
    PREVIEW_QUESTION_PRESETS,
    PROMPT_LABELS,
    BrainBehavior,
    BrainConfig,
    BrainPromptOverrides,
    apply_config_update,
    editor_text_for_prompt,
    export_brain_config_to_path,
    import_brain_config_from_path,
    load_brain_config,
    override_from_editor,
    reset_brain_config,
)
from cluny.brain_client import BrainClient
from cluny.config import Settings
from cluny.ollama_client import OllamaClient
from cluny.user_config import UserConfig, load_user_config, save_user_config


class _PreviewSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


class _PreviewWorker(QRunnable):
    def __init__(self, question: str, prompt_key: str, prompt_text: str, persona: str) -> None:
        super().__init__()
        self._question = question
        self._prompt_key = prompt_key
        self._prompt_text = prompt_text
        self._persona = persona
        self.signals = _PreviewSignals()

    def run(self) -> None:
        try:
            settings = Settings.load()
            cfg = BrainConfig(global_persona=self._persona)
            from cluny.brain_config import get_prompt

            system = get_prompt(
                self._prompt_key,
                settings=settings,
                config=cfg,
                preview_overrides={self._prompt_key: self._prompt_text},
            )
            answer = OllamaClient(settings).chat(system=system, user=self._question)
            self.signals.finished.emit(answer.strip())
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(str(exc))


class BrainEditorDialog(QDialog):
    """Edit brain_config.json and related user preferences."""

    _PROMPT_TABS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Ask / RAG", ("rag_system", "rag_user_template", "rerank_system")),
        ("Propose", ("propose_system",)),
        ("Router", ("router_system",)),
        (
            "Agents",
            (
                "knowledge_agent_system",
                "tasks_agent_system",
                "all_agent_system",
                "planner_agent_system",
            ),
        ),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cluny — Brain Editor")
        self.resize(820, 640)
        self._settings = Settings.load()
        self._user_config = load_user_config(self._settings)
        self._cfg = load_brain_config(self._settings)
        self._client = BrainClient.from_settings(self._settings)
        self._prompt_edits: dict[str, QTextEdit] = {}
        self._thread_pool = QThreadPool.globalInstance()
        self._build_ui()
        self._load_from_config()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        hint = QLabel(
            "Edit Cluny's instructions and behavior. Changes apply to the next message. "
            "Clear a field or match the shipped default to use built-in text."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        general = QWidget()
        general_form = QFormLayout(general)
        self._persona = QTextEdit()
        self._persona.setPlaceholderText("Optional prefix prepended to all system prompts…")
        self._persona.setMaximumHeight(100)
        general_form.addRow("Global persona", self._persona)
        self._tabs.addTab(general, "General")

        for tab_name, keys in self._PROMPT_TABS:
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            for key in keys:
                label = QLabel(PROMPT_LABELS.get(key, key))
                label.setStyleSheet("font-weight: 600; margin-top: 8px;")
                tab_layout.addWidget(label)
                edit = QTextEdit()
                edit.setMinimumHeight(120 if len(keys) == 1 else 80)
                self._prompt_edits[key] = edit
                tab_layout.addWidget(edit)
            tab_layout.addStretch(1)
            self._tabs.addTab(tab, tab_name)

        behavior = QWidget()
        behavior_form = QFormLayout(behavior)
        self._supervisor = QComboBox()
        self._supervisor.addItems(["(use .env default)", "llm", "regex"])
        behavior_form.addRow("Supervisor mode", self._supervisor)
        self._max_proposals = QSpinBox()
        self._max_proposals.setRange(0, 25)
        self._max_proposals.setSpecialValueText("(default 5)")
        behavior_form.addRow("Max proposals", self._max_proposals)
        self._empty_index = QLineEdit()
        self._empty_index.setPlaceholderText("Leave blank for default empty-index message")
        behavior_form.addRow("Empty index message", self._empty_index)
        self._empty_collection = QLineEdit()
        self._empty_collection.setPlaceholderText("Leave blank for default")
        behavior_form.addRow("Empty collection message", self._empty_collection)
        self._tabs.addTab(behavior, "Behavior")

        models = QWidget()
        models_form = QFormLayout(models)
        self._chat_model = QLineEdit()
        models_form.addRow("Chat model", self._chat_model)
        self._embed_model = QLineEdit()
        models_form.addRow("Embed model", self._embed_model)
        self._retrieval_k = QSpinBox()
        self._retrieval_k.setRange(1, 25)
        models_form.addRow("Retrieval k", self._retrieval_k)
        self._hybrid = QDoubleSpinBox()
        self._hybrid.setRange(0.0, 1.0)
        self._hybrid.setSingleStep(0.1)
        models_form.addRow("Vector weight (hybrid)", self._hybrid)
        self._tabs.addTab(models, "Models")

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Preset:"))
        self._preview_preset = QComboBox()
        self._preview_preset.addItem("(custom)", "")
        for q in PREVIEW_QUESTION_PRESETS:
            self._preview_preset.addItem(q[:48] + ("…" if len(q) > 48 else ""), q)
        self._preview_preset.currentIndexChanged.connect(self._on_preview_preset)
        preview_row.addWidget(self._preview_preset)
        preview_row.addWidget(QLabel("Question:"))
        self._preview_question = QLineEdit()
        self._preview_question.setPlaceholderText("e.g. Summarize how you should answer questions")
        self._preview_question.setText(PREVIEW_QUESTION_PRESETS[0])
        preview_row.addWidget(self._preview_question, 1)
        self._preview_btn = QPushButton("Run preview")
        self._preview_btn.clicked.connect(self._run_preview)
        preview_row.addWidget(self._preview_btn)
        root.addLayout(preview_row)

        self._preview_out = QTextEdit()
        self._preview_out.setReadOnly(True)
        self._preview_out.setMaximumHeight(120)
        self._preview_out.setPlaceholderText("Preview uses the active prompt tab (RAG system on General/Ask tabs).")
        root.addWidget(self._preview_out)

        btn_row = QHBoxLayout()
        export_btn = QPushButton("Export…")
        export_btn.clicked.connect(self._export_config)
        import_btn = QPushButton("Import…")
        import_btn.clicked.connect(self._import_config)
        reset_section = QPushButton("Reset section")
        reset_section.clicked.connect(self._reset_section)
        reset_all = QPushButton("Reset all")
        reset_all.clicked.connect(self._reset_all)
        btn_row.addWidget(export_btn)
        btn_row.addWidget(import_btn)
        btn_row.addWidget(reset_section)
        btn_row.addWidget(reset_all)
        btn_row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)
        root.addLayout(btn_row)

    def _load_from_config(self) -> None:
        if self._client is not None:
            try:
                data = self._client.brain_config_get()
                self._apply_remote_state(data)
                return
            except Exception:  # noqa: BLE001
                pass

        self._cfg = load_brain_config(self._settings)
        self._apply_config_to_ui(self._cfg)

    def _apply_config_to_ui(self, cfg: BrainConfig) -> None:
        self._persona.setPlainText(cfg.global_persona)
        for key, edit in self._prompt_edits.items():
            edit.setPlainText(editor_text_for_prompt(key, cfg))

        mode = cfg.behavior.supervisor_mode
        self._supervisor.setCurrentIndex({"llm": 1, "regex": 2}.get(mode or "", 0))
        self._max_proposals.setValue(cfg.behavior.max_proposals or 0)
        self._empty_index.setText(cfg.behavior.empty_index_message or "")
        self._empty_collection.setText(cfg.behavior.empty_collection_message or "")

        self._chat_model.setText(self._user_config.chat_model)
        self._embed_model.setText(self._user_config.embed_model)
        self._retrieval_k.setValue(self._user_config.retrieval_k)
        self._hybrid.setValue(self._user_config.hybrid_vector_weight)

    def _apply_remote_state(self, data: dict) -> None:
        self._persona.setPlainText(str(data.get("global_persona", "")))
        overrides = data.get("overrides") or {}
        defaults = data.get("defaults") or DEFAULT_PROMPTS
        for key, edit in self._prompt_edits.items():
            if overrides.get(key):
                edit.setPlainText(str(overrides[key]))
            else:
                edit.setPlainText(str(defaults.get(key, "")))

        behavior_ov = data.get("behavior_overrides") or {}
        mode = behavior_ov.get("supervisor_mode")
        self._supervisor.setCurrentIndex({"llm": 1, "regex": 2}.get(mode or "", 0))
        self._max_proposals.setValue(int(behavior_ov.get("max_proposals") or 0))
        self._empty_index.setText(str(behavior_ov.get("empty_index_message") or ""))
        self._empty_collection.setText(str(behavior_ov.get("empty_collection_message") or ""))

        self._chat_model.setText(self._user_config.chat_model)
        self._embed_model.setText(self._user_config.embed_model)
        self._retrieval_k.setValue(self._user_config.retrieval_k)
        self._hybrid.setValue(self._user_config.hybrid_vector_weight)

    def _current_prompt_key(self) -> str:
        tab_idx = self._tabs.currentIndex()
        tab_name = self._tabs.tabText(tab_idx)
        for name, keys in self._PROMPT_TABS:
            if name == tab_name and keys:
                return keys[0]
        return "rag_system"

    @Slot()
    def _run_preview(self) -> None:
        key = self._current_prompt_key()
        if key == "rag_user_template":
            QMessageBox.information(
                self,
                "Preview",
                "Preview is not available for the RAG user template (format string). "
                "Switch to the RAG system tab.",
            )
            return

        question = self._preview_question.text().strip()
        if not question:
            return

        self._preview_btn.setEnabled(False)
        self._preview_out.setPlainText("Thinking…")
        worker = _PreviewWorker(
            question,
            key,
            self._prompt_edits[key].toPlainText(),
            self._persona.toPlainText().strip(),
        )
        worker.signals.finished.connect(self._on_preview_done)
        worker.signals.error.connect(self._on_preview_error)
        self._thread_pool.start(worker)

    @Slot(str)
    def _on_preview_done(self, text: str) -> None:
        self._preview_out.setPlainText(text)
        self._preview_btn.setEnabled(True)

    @Slot(str)
    def _on_preview_error(self, message: str) -> None:
        self._preview_out.setPlainText(f"Error: {message}")
        self._preview_btn.setEnabled(True)

    def _collect_prompts(self) -> dict[str, str | None]:
        return {
            key: override_from_editor(edit.toPlainText(), key)
            for key, edit in self._prompt_edits.items()
        }

    def _collect_behavior(self) -> dict[str, str | int | None]:
        sup_idx = self._supervisor.currentIndex()
        supervisor = None if sup_idx == 0 else self._supervisor.currentText()
        max_p = self._max_proposals.value()
        return {
            "supervisor_mode": supervisor,
            "max_proposals": max_p if max_p > 0 else None,
            "empty_index_message": self._empty_index.text().strip() or None,
            "empty_collection_message": self._empty_collection.text().strip() or None,
        }

    def _collect_brain_config(self) -> BrainConfig:
        return BrainConfig(
            global_persona=self._persona.toPlainText().strip(),
            prompts=BrainPromptOverrides.from_dict(self._collect_prompts()),
            behavior=BrainBehavior.from_dict(self._collect_behavior()),
        )

    @Slot(int)
    def _on_preview_preset(self, index: int) -> None:
        text = self._preview_preset.itemData(index)
        if text:
            self._preview_question.setText(str(text))

    @Slot()
    def _export_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export brain config",
            "brain_config.json",
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            data = self._collect_brain_config().to_dict()
            Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            QMessageBox.information(self, "Exported", f"Brain config saved to:\n{path}")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    @Slot()
    def _import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import brain config",
            "",
            "JSON files (*.json)",
        )
        if not path:
            return
        reply = QMessageBox.question(
            self,
            "Import brain config",
            "Replace the current editor contents with the imported file? "
            "Click Save to persist to your data directory.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            from cluny.brain_config import validate_brain_config_dict

            cfg = validate_brain_config_dict(data)
            self._cfg = cfg
            self._apply_config_to_ui(cfg)
            QMessageBox.information(
                self,
                "Imported",
                "Config loaded into the editor. Click Save to apply permanently.",
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    @Slot()
    def _save(self) -> None:
        reply = QMessageBox.question(
            self,
            "Save brain config",
            "Save changes to Cluny's instructions? They apply to the next message.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Save:
            return

        persona = self._persona.toPlainText().strip()
        prompts = self._collect_prompts()
        behavior = self._collect_behavior()

        try:
            if self._client is not None:
                self._client.brain_config_put(
                    global_persona=persona,
                    prompts=prompts,
                    behavior=behavior,
                )
            else:
                apply_config_update(
                    self._settings,
                    global_persona=persona,
                    prompts=prompts,
                    behavior=behavior,
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Save failed", str(exc))
            return

        self._user_config = UserConfig(
            chat_model=self._chat_model.text().strip() or self._user_config.chat_model,
            embed_model=self._embed_model.text().strip() or self._user_config.embed_model,
            retrieval_k=self._retrieval_k.value(),
            hybrid_vector_weight=self._hybrid.value(),
            agent_mode=self._user_config.agent_mode,
            ask_collection=self._user_config.ask_collection,
            standalone_mode=self._user_config.standalone_mode,
            first_run_complete=self._user_config.first_run_complete,
        )
        save_user_config(self._settings, self._user_config)
        self.accept()

    @Slot()
    def _reset_section(self) -> None:
        tab_idx = self._tabs.currentIndex()
        tab_name = self._tabs.tabText(tab_idx)
        if tab_name == "General":
            self._persona.clear()
            return
        if tab_name == "Behavior":
            self._supervisor.setCurrentIndex(0)
            self._max_proposals.setValue(0)
            self._empty_index.clear()
            self._empty_collection.clear()
            return
        if tab_name == "Models":
            QMessageBox.information(
                self,
                "Reset section",
                "Model settings are stored in user_config.json. Re-open Settings to reset.",
            )
            return
        for name, keys in self._PROMPT_TABS:
            if name == tab_name:
                for key in keys:
                    self._prompt_edits[key].setPlainText(DEFAULT_PROMPTS[key])
                return

    @Slot()
    def _reset_all(self) -> None:
        reply = QMessageBox.warning(
            self,
            "Reset all",
            "Reset all brain instructions to shipped defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if self._client is not None:
                self._client.brain_config_reset(reset_all=True)
            else:
                reset_brain_config(self._settings, reset_all=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Reset failed", str(exc))
            return
        self._load_from_config()


def export_brain_config_dialog(parent: QWidget | None = None) -> bool:
    """Export saved brain_config.json to a user-chosen file."""
    settings = Settings.load()
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "Export brain config",
        "brain_config.json",
        "JSON files (*.json)",
    )
    if not path:
        return False
    try:
        export_brain_config_to_path(settings, Path(path))
        QMessageBox.information(parent, "Exported", f"Brain config saved to:\n{path}")
        return True
    except OSError as exc:
        QMessageBox.warning(parent, "Export failed", str(exc))
        return False


def import_brain_config_dialog(parent: QWidget | None = None) -> bool:
    """Import brain_config.json from disk into CLUNY_DATA_DIR."""
    settings = Settings.load()
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Import brain config",
        "",
        "JSON files (*.json)",
    )
    if not path:
        return False
    reply = QMessageBox.question(
        parent,
        "Import brain config",
        "Replace your saved brain config with this file?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return False
    try:
        import_brain_config_from_path(settings, Path(path))
        QMessageBox.information(
            parent,
            "Imported",
            "Brain config imported. Changes apply to the next message.",
        )
        return True
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        QMessageBox.warning(parent, "Import failed", str(exc))
        return False


def open_brain_editor(parent: QWidget | None = None) -> bool:
    """Show Brain Editor; returns True if saved."""
    dlg = BrainEditorDialog(parent)
    return dlg.exec() == QDialog.DialogCode.Accepted
