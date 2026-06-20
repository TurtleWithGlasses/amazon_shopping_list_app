"""Async product-image loading + on-disk cache.

Thumbnails are downloaded once on a worker thread, cached under
%LOCALAPPDATA%\\PriceTracker\\images, and applied to a QLabel on the GUI thread.
QPixmap isn't thread-safe, so workers only return raw bytes; the conversion to a
pixmap happens here, in the GUI thread.
"""
import hashlib

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QPixmap

from core.paths import app_data_dir

_CACHE_DIR = app_data_dir() / "images"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _cache_path(url: str):
    return _CACHE_DIR / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".img")


class _Signals(QObject):
    done = Signal(str, object)  # url, bytes | None


class _DownloadTask(QRunnable):
    def __init__(self, url: str, path):
        super().__init__()
        self.url = url
        self.path = path
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        content = None
        try:
            import requests
            resp = requests.get(self.url, headers=_REQUEST_HEADERS, timeout=15)
            if resp.status_code == 200 and resp.content:
                content = resp.content
                self.path.write_bytes(content)
        except Exception:
            content = None
        try:
            self.signals.done.emit(self.url, content)
        except RuntimeError:
            pass


class ImageLoader(QObject):
    """Owned by the main window (GUI thread)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._pixmaps = {}     # url -> QPixmap
        self._pending = {}     # url -> list of (label, size)

    def load(self, url, label, size: int) -> None:
        if not url:
            return
        if url in self._pixmaps:
            self._apply(label, self._pixmaps[url], size)
            return
        path = _cache_path(url)
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self._pixmaps[url] = pixmap
                self._apply(label, pixmap, size)
                return
        self._pending.setdefault(url, []).append((label, size))
        if len(self._pending[url]) == 1:  # only the first request starts a download
            task = _DownloadTask(url, path)
            task.signals.done.connect(self._on_done)
            self._pool.start(task)

    def _on_done(self, url, content) -> None:
        pixmap = QPixmap()
        if content:
            pixmap.loadFromData(content)
        if not pixmap.isNull():
            self._pixmaps[url] = pixmap
        for label, size in self._pending.pop(url, []):
            if not pixmap.isNull():
                self._apply(label, pixmap, size)

    @staticmethod
    def _apply(label, pixmap: QPixmap, size: int) -> None:
        try:
            label.setPixmap(pixmap.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        except RuntimeError:
            pass  # the row (and its label) was rebuilt before the image arrived
