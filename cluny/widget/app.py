"""Unified Cluny app: menu bar widget (default) + optional full window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from cluny.app_mode import configure_app_environment
from cluny.brain_service import ensure_brain_running, stop_spawned_serve
from cluny.config import Settings, load_dotenv_if_present
from cluny.gui.main_window import MainWindow
from cluny.user_config import load_user_config, save_user_config
from cluny.widget.tray import ClunyTray
from cluny.widget.welcome import WelcomeDialog


def _set_macos_dock_visible(visible: bool) -> None:
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (  # type: ignore[import-untyped]
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
            NSApp,
        )

        policy = (
            NSApplicationActivationPolicyRegular
            if visible
            else NSApplicationActivationPolicyAccessory
        )
        NSApp.setActivationPolicy_(policy)
    except ImportError:
        pass


def run_widget_app(*, start_full: bool = False) -> None:
    """Start menu bar widget; optionally open full window on launch."""
    configure_app_environment()
    load_dotenv_if_present()

    settings = Settings.load()
    if settings.brain_url:
        health = ensure_brain_running(settings)
        if not health.ok:
            print(f"Warning: brain not reachable: {health.message}", file=sys.stderr)

    app = QApplication(sys.argv)
    app.setApplicationName("Cluny")
    app.setApplicationDisplayName("Cluny")
    app.setOrganizationName("Cluny")
    app.setQuitOnLastWindowClosed(False)

    user_config = load_user_config(settings)
    show_full = start_full

    if not user_config.first_run_complete:
        _set_macos_dock_visible(True)
        dlg = WelcomeDialog()
        if dlg.exec():
            show_full = dlg.wants_library()
        user_config.first_run_complete = True
        save_user_config(settings, user_config)

    _set_macos_dock_visible(show_full)

    main_window: MainWindow | None = None

    def open_full_window() -> None:
        nonlocal main_window
        _set_macos_dock_visible(True)
        if main_window is None:
            main_window = MainWindow()
            main_window.destroyed.connect(lambda: _set_macos_dock_visible(False))
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

    def quit_app() -> None:
        if main_window is not None:
            main_window.close()
        stop_spawned_serve()
        app.quit()

    tray = ClunyTray(on_open_full=open_full_window, on_quit=quit_app)
    tray.show()

    if show_full:
        open_full_window()

    sys.exit(app.exec())
