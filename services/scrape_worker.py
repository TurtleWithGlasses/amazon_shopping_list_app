"""Background scraping so the UI never blocks on Selenium (10-30s per page)."""
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.scraping import ProductData, scrape


class ScrapeSignals(QObject):
    # (key, ProductData) — key lets the UI know which row a result belongs to
    finished = Signal(object, object)


class ScrapeTask(QRunnable):
    """Runs one scrape on the global QThreadPool and emits the result."""

    def __init__(self, url: str, key=None):
        super().__init__()
        self.url = url
        self.key = key
        self.signals = ScrapeSignals()

    @Slot()
    def run(self) -> None:
        try:
            data = scrape(self.url)
        except Exception as exc:  # never let a worker thread crash the app
            data = ProductData(url=self.url, error=str(exc))
        try:
            self.signals.finished.emit(self.key, data)
        except RuntimeError:
            # UI was torn down (app quitting) while this scrape was still running.
            pass
