"""Menu bar tray icon and popover controller."""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from cluny.widget.panel import WidgetPanel


def _make_tray_icon() -> QIcon:
    pixmap = QPixmap(22, 22)
    pixmap.fill(QColor("#2563eb"))
    icon = QIcon(pixmap)
    return icon


class ClunyTray:
    """System tray + popover; opens full window via callback."""

    def __init__(
        self,
        *,
        on_open_full: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_open_full = on_open_full
        self._on_quit = on_quit
        self._panel = WidgetPanel()

        self._tray = QSystemTrayIcon(_make_tray_icon())
        self._tray.setToolTip("Cluny")

        menu = QMenu()
        show_action = QAction("Show panel", menu)
        show_action.triggered.connect(self.show_panel)
        menu.addAction(show_action)

        full_action = QAction("Open full window", menu)
        full_action.triggered.connect(self._on_open_full)
        menu.addAction(full_action)

        menu.addSeparator()
        quit_action = QAction("Quit Cluny", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)

    def show(self) -> None:
        self._tray.show()
        if sys.platform == "darwin":
            self._tray.showMessage(
                "Cluny",
                "Menu bar widget is running. Click the icon for Ask / Capture / Task.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def show_panel(self) -> None:
        self._position_panel()
        self._panel.show_and_focus()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self._panel.isVisible():
                self._panel.hide()
            else:
                self.show_panel()

    def _position_panel(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        tray_geo: QRect = self._tray.geometry()
        panel_w = self._panel.width()
        panel_h = self._panel.height()

        if tray_geo.isValid() and tray_geo.width() > 0:
            x = tray_geo.x() - panel_w // 2 + tray_geo.width() // 2
            y = tray_geo.y() + tray_geo.height() + 4
        else:
            avail = screen.availableGeometry()
            x = avail.right() - panel_w - 16
            y = avail.top() + 8

        self._panel.move(QPoint(max(8, x), max(8, y)))
