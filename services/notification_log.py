"""In-app notifications history (Phase 40).

A small append-only log of the price/stock/target changes surfaced after each
refresh, so the user can review them inside the app (the bell button) rather than
only via tray/Telegram. Persisted as JSON next to the database so history
survives restarts; capped so it can't grow without bound. All I/O degrades
gracefully — a missing/corrupt file just starts an empty log.

Each entry is a plain dict with at least: ``ts`` (ISO-8601 UTC), ``site``,
``name``, ``detail`` (pre-formatted change text), ``kind``, and ``read``.
"""
import json
from pathlib import Path

_MAX_ENTRIES = 200


class NotificationLog:
    def __init__(self, path):
        self._path = Path(path)
        self._entries = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._entries = [e for e in data if isinstance(e, dict)]
        except Exception:
            self._entries = []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._entries, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def add(self, entries) -> None:
        """Append new (unread) entries, newest kept, oldest trimmed past the cap."""
        for entry in entries:
            item = dict(entry)
            item.setdefault("read", False)
            self._entries.append(item)
        if len(self._entries) > _MAX_ENTRIES:
            self._entries = self._entries[-_MAX_ENTRIES:]
        self._save()

    def all(self):
        """All entries, newest first."""
        return list(reversed(self._entries))

    def unread_count(self) -> int:
        return sum(1 for e in self._entries if not e.get("read"))

    def mark_all_read(self) -> None:
        changed = False
        for entry in self._entries:
            if not entry.get("read"):
                entry["read"] = True
                changed = True
        if changed:
            self._save()

    def clear(self) -> None:
        self._entries = []
        self._save()
