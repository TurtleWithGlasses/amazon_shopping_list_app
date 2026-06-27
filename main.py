"""Price Tracker — desktop application entry point.

Run during development with:  venv\\Scripts\\python main.py
"""
import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

from core.cloud.config import is_configured
from core.db import init_db
from ui.icons import app_icon
from ui.main_window import MainWindow
from ui.theme import DEFAULT_THEME, apply_theme


def _is_invalid_refresh_token(exc: Exception) -> bool:
    """True only for a definitive auth failure (bad/expired/used refresh token),
    NOT a transient/network error. Right after a PC restart the network is often
    not up yet, so restoring the session throws a connection error — we must keep
    the saved "remember me" token in that case instead of logging the user out."""
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    if status in (400, 401, 403):
        return True
    msg = str(exc).lower()
    return "refresh token" in msg and any(
        w in msg for w in ("invalid", "not found", "expired", "already used", "revoked")
    )


def _ensure_logged_in() -> bool:
    """Log in via a saved session or the login dialog. False if the user cancels."""
    import time

    from core.cloud import auth, session_store
    from ui.login_dialog import LoginDialog

    if auth.is_logged_in():
        return True
    token = session_store.load_refresh_token()
    if token:
        for attempt in range(4):
            try:
                auth.restore_session(token)
                # Supabase rotates refresh tokens — persist the new one.
                session_store.save_session(auth.current_refresh_token(), auth.current_email() or "")
                return True
            except Exception as exc:
                if _is_invalid_refresh_token(exc):
                    session_store.clear_session()  # genuine → fall back to login
                    break
                # Transient (e.g. no network yet after boot): keep the saved
                # session and retry briefly rather than logging the user out.
                if attempt < 3:
                    time.sleep(2)
                else:
                    break  # still offline — keep the token; next launch retries
    return LoginDialog().exec() == QDialog.DialogCode.Accepted


def _run_cloud(app: QApplication) -> None:
    """Login → main window loop. Logout returns to the login screen."""
    from core import datastore
    from core.cloud import auth, repository as cloud_repo, session_store

    while True:
        if not _ensure_logged_in():
            return  # cancelled → exit app
        datastore.set_backend(cloud_repo)
        window = MainWindow()
        window.show()
        app.exec()
        if getattr(window, "logout_requested", False):
            auth.sign_out()
            session_store.clear_session()
            continue  # require sign-in again
        return  # normal quit


def _set_windows_app_id() -> None:
    # Without an explicit AppUserModelID, Windows shows the python.exe icon in the
    # taskbar instead of our window icon when running as a script.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PriceTracker.App")
        except Exception:
            pass


def main() -> None:
    _set_windows_app_id()
    init_db()  # local SQLite cache schema in %LOCALAPPDATA%\PriceTracker
    app = QApplication(sys.argv)
    app.setApplicationName("Price Tracker")
    app.setOrganizationName("PriceTracker")
    app.setWindowIcon(app_icon())
    apply_theme(app, QSettings().value("theme", DEFAULT_THEME))

    if is_configured():
        _run_cloud(app)
    else:
        window = MainWindow()
        window.show()
        app.exec()
    sys.exit(0)


if __name__ == "__main__":
    main()
