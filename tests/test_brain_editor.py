"""Tests for Brain Editor dialog helpers (no full Qt event loop)."""

from __future__ import annotations

import sys

import pytest

from cluny.brain_config import (
    DEFAULT_PROMPTS,
    editor_text_for_prompt,
    invalidate_brain_config_cache,
    load_brain_config,
)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_brain_editor_dialog_loads_defaults(qapp, settings, monkeypatch):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(settings.data_dir))
    invalidate_brain_config_cache()
    from cluny.gui.brain_editor import BrainEditorDialog

    dlg = BrainEditorDialog()
    cfg = load_brain_config(settings)
    assert dlg._persona.toPlainText() == cfg.global_persona
    assert dlg._prompt_edits["rag_system"].toPlainText() == editor_text_for_prompt(
        "rag_system", cfg
    )


def test_brain_editor_collect_prompts_roundtrip(qapp, settings, monkeypatch):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(settings.data_dir))
    invalidate_brain_config_cache()
    from cluny.brain_config import apply_config_update
    from cluny.gui.brain_editor import BrainEditorDialog

    dlg = BrainEditorDialog()
    dlg._prompt_edits["rag_system"].setPlainText("My custom RAG.")
    prompts = dlg._collect_prompts()
    assert prompts["rag_system"] == "My custom RAG."
    apply_config_update(settings, prompts=prompts)
    cfg = load_brain_config(settings)
    assert cfg.prompts.rag_system == "My custom RAG."
    dlg2 = BrainEditorDialog()
    assert dlg2._prompt_edits["rag_system"].toPlainText() == "My custom RAG."
