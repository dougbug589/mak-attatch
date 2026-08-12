#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication

from core import attacher
from ui.main_window import MainWindow

DARK_QSS = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e1e2e;
}
QLineEdit, QListWidget, QTableWidget, QComboBox, QTextEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px;
    selection-background-color: #cba6f7;
    selection-color: #11111b;
}
QLineEdit:focus, QListWidget:focus, QTableWidget:focus, QComboBox:focus {
    border-color: #89b4fa;
}
QPushButton {
    background-color: #45475a;
    border: none;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #585b70; }
QPushButton:pressed { background-color: #6c7086; }
QPushButton:disabled { background-color: #313244; color: #6c7086; }
QPushButton:default {
    background-color: #cba6f7;
    color: #11111b;
}
QToolBar {
    background-color: #313244;
    border: none;
    spacing: 6px;
    padding: 6px;
}
QToolButton {
    background: transparent;
    color: #cdd6f4;
    padding: 4px 12px;
    border-radius: 4px;
}
QToolButton:hover { background-color: #45475a; }
QCheckBox, QRadioButton { color: #cdd6f4; }
QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}
QProgressBar::chunk { background-color: #a6e3a1; border-radius: 4px; }
QStatusBar { background-color: #313244; color: #a6adc8; }
QMenu { background-color: #313244; border: 1px solid #45475a; }
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background-color: #45475a; }
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
}
QTableWidget { gridline-color: #45475a; }
QScrollBar:vertical { background: #313244; width: 10px; }
QScrollBar::handle:vertical { background: #585b70; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #6c7086; }
QScrollBar:horizontal { background: #313244; height: 10px; }
QScrollBar::handle:horizontal { background: #585b70; border-radius: 5px; }
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
}
QSplitter::handle { background-color: #313244; }
QLabel { color: #cdd6f4; }
"""


def main():
    missing = attacher.check_tools()
    if missing:
        print(f"Missing required tools: {', '.join(missing)}")
        print("Install them with your package manager")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("mak-attatch")
    app.setOrganizationName("mak-attatch")
    app.setStyleSheet(DARK_QSS)
    QGuiApplication.setDesktopFileName("mak-attatch")
    icon_path = Path(__file__).resolve().parent / "assets" / "logo.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
