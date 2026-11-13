"""Desktop GUI entry point (``mak-attatch``)."""
import sys
import threading
import traceback
from pathlib import Path

from mak_attatch.core import attacher, deps, tmdb

try:
    from PyQt6.QtGui import QGuiApplication, QIcon
    from PyQt6.QtWidgets import QApplication, QMessageBox
except ImportError:  # GUI extra not installed; main() explains how to fix it
    QApplication = None

GUI_MISSING = (
    "The desktop GUI needs PyQt6, which is not installed.\n"
    "Install it with:  pip install 'mak-attatch[gui]'   (Arch: python-pyqt6)\n"
    "The terminal UI (mak-attatch-tui) and CLI (mak-attatch-cli) work without it."
)

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


def _install_excepthook():
    """Report unexpected errors instead of letting PyQt abort the process.

    Without a custom sys.excepthook, PyQt6 calls qFatal() on any exception
    that escapes a slot, killing the app (and any file write in progress).
    """
    def hook(exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb)
        if threading.current_thread() is not threading.main_thread():
            return  # widgets may only be touched from the GUI thread
        QMessageBox.critical(
            None, "Unexpected error",
            f"{exc_type.__name__}: {tmdb.redact(str(exc))}\n\n"
            "The action was aborted; the app is still running.",
        )

    sys.excepthook = hook


def main():
    if QApplication is None:
        print(GUI_MISSING, file=sys.stderr)
        sys.exit(1)
    from mak_attatch.ui.main_window import MainWindow

    missing = attacher.check_tools()
    if missing:
        print(f"Missing required tools: {', '.join(missing)}")
        print(deps.hint(missing))
        sys.exit(1)

    app = QApplication(sys.argv)
    _install_excepthook()
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
