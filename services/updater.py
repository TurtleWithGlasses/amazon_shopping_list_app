"""Update checker + downloader.

Checks the latest GitHub release; if newer, can download the attached installer
(.exe) and hand it to the app to run. Note: the downloaded installer is unsigned,
so Windows SmartScreen may warn on first run ("More info → Run anyway").
"""
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.version import GITHUB_REPO, __version__

_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_DOWNLOAD_NAME = "PriceTracker-Update-Setup.exe"


@dataclass
class UpdateInfo:
    latest: str                      # e.g. "0.2.0"
    url: str                         # release page
    asset_url: Optional[str] = None  # direct download URL of the installer .exe


def _parse_version(value: str) -> Tuple[int, ...]:
    cleaned = value.strip().lstrip("vV")
    parts = []
    for piece in cleaned.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_for_update(timeout: float = 10.0) -> Optional[UpdateInfo]:
    """Return UpdateInfo if a newer release exists, else None (also on error or
    when the repo has no releases)."""
    import requests
    try:
        resp = requests.get(
            _API, timeout=timeout, headers={"Accept": "application/vnd.github+json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name") or data.get("name") or ""
        if not tag or _parse_version(tag) <= _parse_version(__version__):
            return None
        # Prefer the self-contained INSTALLER (e.g. PriceTracker-Setup.exe) over a
        # bare one-folder app exe, which can't run on its own.
        exe_assets = [
            (asset.get("name") or "", asset.get("browser_download_url"))
            for asset in data.get("assets", [])
            if (asset.get("name") or "").lower().endswith(".exe")
        ]
        asset_url = next(
            (dl for name, dl in exe_assets
             if "setup" in name.lower() or "install" in name.lower()),
            None,
        )
        if asset_url is None and exe_assets:
            asset_url = exe_assets[0][1]
        url = data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases"
        return UpdateInfo(latest=tag.lstrip("vV"), url=url, asset_url=asset_url)
    except Exception:
        return None


def download_installer(asset_url: str, on_progress=None) -> str:
    """Stream the installer to a temp file; returns its path."""
    import requests
    dest = os.path.join(tempfile.gettempdir(), _DOWNLOAD_NAME)
    with requests.get(asset_url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        on_progress(done, total)
    return dest


class _CheckSignals(QObject):
    finished = Signal(object)  # UpdateInfo | None


class UpdateCheckTask(QRunnable):
    """Runs check_for_update off the GUI thread."""

    def __init__(self):
        super().__init__()
        self.signals = _CheckSignals()

    @Slot()
    def run(self) -> None:
        try:
            info = check_for_update()
        except Exception:
            info = None
        try:
            self.signals.finished.emit(info)
        except RuntimeError:
            pass


class _DownloadSignals(QObject):
    progress = Signal(int, int)  # done, total
    finished = Signal(object)    # path | None


class DownloadTask(QRunnable):
    """Downloads the installer off the GUI thread."""

    def __init__(self, asset_url: str):
        super().__init__()
        self.asset_url = asset_url
        self.signals = _DownloadSignals()

    @Slot()
    def run(self) -> None:
        path = None
        try:
            path = download_installer(
                self.asset_url,
                on_progress=lambda d, t: self.signals.progress.emit(d, t),
            )
        except Exception:
            path = None
        try:
            self.signals.finished.emit(path)
        except RuntimeError:
            pass
