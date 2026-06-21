"""Update checker: compares the running version against the latest GitHub release.

v1 = notify + open the release page. No auto-download yet (that needs code
signing to avoid SmartScreen — see BUILD.md).
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.version import GITHUB_REPO, __version__

_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


@dataclass
class UpdateInfo:
    latest: str   # e.g. "0.2.0"
    url: str      # release page


def _parse_version(value: str) -> Tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = []
    for piece in cleaned.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_for_update(timeout: float = 10.0) -> Optional[UpdateInfo]:
    """Return UpdateInfo if a newer release exists, else None (also on any error
    or when the repo has no releases yet)."""
    import requests
    try:
        resp = requests.get(
            _API, timeout=timeout, headers={"Accept": "application/vnd.github+json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name") or data.get("name") or ""
        if not tag:
            return None
        if _parse_version(tag) > _parse_version(__version__):
            url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases"
            return UpdateInfo(latest=tag.lstrip("vV"), url=url)
    except Exception:
        return None
    return None


class _Signals(QObject):
    finished = Signal(object)  # UpdateInfo | None


class UpdateCheckTask(QRunnable):
    """Runs check_for_update off the GUI thread."""

    def __init__(self):
        super().__init__()
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            info = check_for_update()
        except Exception:
            info = None
        try:
            self.signals.finished.emit(info)
        except RuntimeError:
            pass  # UI gone
