#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from core import attacher
from ui.main_window import MainWindow


def main():
    missing = attacher.check_tools()
    if missing:
        print(f"Missing required tools: {', '.join(missing)}")
        print("Install them with your package manager")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("mak-attatch")
    app.setOrganizationName("mak-attatch")
    icon_path = Path(__file__).resolve().parent / "assets" / "logo.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
