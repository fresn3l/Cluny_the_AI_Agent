"""First-run welcome for Cluny.app."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class WelcomeDialog(QDialog):
    """One-time welcome: open full library window or stay in menu bar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to Cluny")
        self.setMinimumWidth(360)
        self._open_library = False

        lay = QVBoxLayout(self)
        title = QLabel("Cluny is your local second brain.")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(title)

        body = QLabel(
            "Use the menu bar icon for quick Ask, Capture, and work proposals.\n\n"
            "Open the full window when you want the library sidebar, long chats, "
            "and drag-drop ingest."
        )
        body.setWordWrap(True)
        lay.addWidget(body)

        open_btn = QPushButton("Open library window")
        open_btn.clicked.connect(self._choose_library)
        lay.addWidget(open_btn)

        stay_btn = QPushButton("Stay in menu bar")
        stay_btn.clicked.connect(self.accept)
        lay.addWidget(stay_btn)

        skip = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        skip.rejected.connect(self.reject)
        lay.addWidget(skip)

    def _choose_library(self) -> None:
        self._open_library = True
        self.accept()

    def wants_library(self) -> bool:
        return self._open_library
