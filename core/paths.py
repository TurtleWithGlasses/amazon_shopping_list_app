"""Filesystem locations for the desktop app.

The live database lives in the per-user application-data directory (NOT in a
cloud-synced folder — sync clients corrupt live SQLite files). Backing the DB
up to Google Drive happens later as a snapshot copy, not as the live store.
"""
import os
import sys
from pathlib import Path

APP_NAME = "PriceTracker"


def app_data_dir() -> Path:
    """Per-user, per-OS application-data directory, created if missing."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    directory = Path(base) / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def database_path() -> Path:
    """Path to the SQLite database file.

    Honors the PRICETRACKER_DB_PATH environment variable (used by tests) so the
    real AppData database is never touched during development.
    """
    override = os.environ.get("PRICETRACKER_DB_PATH")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return app_data_dir() / "app.db"


def notifications_path() -> Path:
    """Path to the in-app notifications history (JSON). Sits next to the DB so it
    follows the same test override, keeping the real history out of dev runs."""
    return database_path().parent / "notifications.json"
