"""Price Tracker — desktop application entry point.

Run during development with:  venv\\Scripts\\python main.py
"""
import sys

from PySide6.QtWidgets import QApplication, QDialog

from core.cloud.config import is_configured
from core.db import init_db
from ui.main_window import MainWindow


def main() -> None:
    init_db()  # local SQLite cache schema in %LOCALAPPDATA%\PriceTracker
    app = QApplication(sys.argv)
    app.setApplicationName("Price Tracker")
    app.setOrganizationName("PriceTracker")

    # If Supabase is configured, require login and use the cloud backend.
    if is_configured():
        from core import datastore
        from core.cloud import repository as cloud_repo
        from ui.login_dialog import LoginDialog

        login = LoginDialog()
        if login.exec() != QDialog.DialogCode.Accepted:
            return  # user cancelled the login dialog
        datastore.set_backend(cloud_repo)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
