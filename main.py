"""Price Tracker — desktop application entry point.

Run during development with:  venv\\Scripts\\python main.py
"""
import sys

from PySide6.QtWidgets import QApplication

from core.db import init_db
from ui.main_window import MainWindow


def main() -> None:
    init_db()  # create the SQLite schema in %LOCALAPPDATA%\PriceTracker on first run
    app = QApplication(sys.argv)
    app.setApplicationName("Price Tracker")
    app.setOrganizationName("PriceTracker")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
