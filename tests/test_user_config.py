"""Tests for user_config persistence and settings dialog fields."""

from __future__ import annotations

import json
import sys

import pytest

from cluny.user_config import UserConfig, config_path, load_user_config, save_user_config


def test_standalone_mode_roundtrip(settings):
    cfg = UserConfig(standalone_mode=True, first_run_complete=True, ask_collection="research")
    save_user_config(settings, cfg)
    loaded = load_user_config(settings)
    assert loaded.standalone_mode is True
    assert loaded.first_run_complete is True
    assert loaded.ask_collection == "research"


def test_standalone_mode_defaults_false(settings):
    cfg = load_user_config(settings)
    assert cfg.standalone_mode is False


def test_config_written_to_data_dir(settings):
    save_user_config(settings, UserConfig(standalone_mode=True))
    path = config_path(settings)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["standalone_mode"] is True


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_settings_dialog_preserves_standalone_mode(qapp, settings):
    from cluny.gui.main_window import _SettingsDialog

    base = UserConfig(
        standalone_mode=False,
        ask_collection="notes",
        first_run_complete=True,
        agent_mode="chat",
    )
    dlg = _SettingsDialog(None, base)
    dlg._standalone.setChecked(True)
    result = dlg.result_config()
    assert result.standalone_mode is True
    assert result.ask_collection == "notes"
    assert result.first_run_complete is True
    assert result.agent_mode == "chat"
