"""Application entry: QApplication and event loop."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from cluny.config import load_dotenv_if_present
from cluny.gui.main_window import MainWindow


def run_app() -> None:
    load_dotenv_if_present()
    app = QApplication(sys.argv)
    app.setApplicationName("Cluny")
    app.setApplicationDisplayName("Cluny")
    app.setOrganizationName("Cluny")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
