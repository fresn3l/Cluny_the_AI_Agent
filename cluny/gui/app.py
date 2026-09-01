"""Application entry: QApplication and event loop."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from cluny.app_mode import configure_app_environment
from cluny.brain_service import ensure_brain_running, stop_spawned_serve
from cluny.config import Settings, load_dotenv_if_present
from cluny.gui.main_window import MainWindow


def run_app() -> None:
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
    app.aboutToQuit.connect(stop_spawned_serve)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
