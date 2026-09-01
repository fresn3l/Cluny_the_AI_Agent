"""Shared styles for widget UI."""

WIDGET_STYLESHEET = """
QWidget {
    background-color: #1e1e1e;
    color: #ececec;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #3c3c3c;
    border-radius: 8px;
    background: #252526;
}
QTabBar::tab {
    background: #2d2d2d;
    color: #a0a0a0;
    padding: 8px 14px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #252526;
    color: #ececec;
}
QTextEdit, QLineEdit {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 8px;
    color: #ececec;
}
QPushButton {
    background-color: #3a3a3a;
    border: 1px solid #555;
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton:hover { background-color: #454545; }
QPushButton#primaryBtn {
    background-color: #2563eb;
    border: none;
    color: #fff;
    font-weight: 600;
}
QPushButton#primaryBtn:hover { background-color: #1d4ed8; }
QPushButton:disabled { color: #666; }
QLabel#statusLabel { color: #a0a0a0; font-size: 12px; }
QLabel#answerLabel {
    background-color: #2d2d2d;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 10px;
}
"""
