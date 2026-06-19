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
        from core.cloud import auth, repository as cloud_repo, session_store
        from ui.login_dialog import LoginDialog

        logged_in = False
        token = session_store.load_refresh_token()
        if token:
            try:
                auth.restore_session(token)
                # Supabase rotates refresh tokens — persist the new one.
                session_store.save_session(auth.current_refresh_token(), auth.current_email() or "")
                logged_in = True
            except Exception:
                session_store.clear_session()  # expired/invalid → fall back to login

        if not logged_in:
            login = LoginDialog()
            if login.exec() != QDialog.DialogCode.Accepted:
                return  # user cancelled the login dialog

        datastore.set_backend(cloud_repo)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
