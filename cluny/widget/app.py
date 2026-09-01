"""Unified Cluny app: menu bar widget (default) + optional full window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from cluny.config import load_dotenv_if_present
from cluny.gui.main_window import MainWindow
from cluny.widget.tray import ClunyTray


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
    load_dotenv_if_present()
    app = QApplication(sys.argv)
    app.setApplicationName("Cluny")
    app.setApplicationDisplayName("Cluny")
    app.setOrganizationName("Cluny")
    app.setQuitOnLastWindowClosed(False)

    _set_macos_dock_visible(start_full)

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
        app.quit()

    tray = ClunyTray(on_open_full=open_full_window, on_quit=quit_app)
    tray.show()

    if start_full:
        open_full_window()

    sys.exit(app.exec())
