"""Tests for full-window GUI HTTP bootstrap."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cluny.brain_service import BrainHealth


def test_run_app_configures_http_brain(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr("cluny.gui.app.configure_app_environment", lambda: calls.append("configure"))
    monkeypatch.setattr("cluny.gui.app.load_dotenv_if_present", lambda: calls.append("dotenv"))

    class FakeSettings:
        brain_url = "http://127.0.0.1:8787"

    monkeypatch.setattr(
        "cluny.gui.app.Settings.load",
        lambda: FakeSettings(),
    )
    monkeypatch.setattr(
        "cluny.gui.app.ensure_brain_running",
        lambda settings: calls.append("ensure") or BrainHealth(
            ok=True, brain_ready=True, message=None, ollama_ok=True
        ),
    )
    monkeypatch.setattr("cluny.gui.app.stop_spawned_serve", lambda: calls.append("stop"))

    app_instance = MagicMock()

    with (
        patch("cluny.gui.app.QApplication", return_value=app_instance) as mock_app,
        patch("cluny.gui.app.MainWindow") as mock_window,
        patch("cluny.gui.app.sys.exit") as mock_exit,
    ):
        from cluny.gui.app import run_app

        run_app()

    assert calls[:3] == ["configure", "dotenv", "ensure"]
    mock_app.assert_called_once()
    app_instance.aboutToQuit.connect.assert_called_once()
    mock_window.return_value.show.assert_called_once()
    mock_exit.assert_called_once()
