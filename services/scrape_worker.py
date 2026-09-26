"""Background scraping so the UI never blocks on Selenium (10-30s per page)."""
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.scraping import ProductData, scrape
from core.scraping.browser import set_cancel_token


class ScrapeSignals(QObject):
    # (key, ProductData) — key lets the UI know which row a result belongs to
    finished = Signal(object, object)


class ScrapeTask(QRunnable):
    """Runs one scrape on a QThreadPool and emits the result.

    `token` (a CancelToken) ties the task to a refresh run so Stop can abort it:
    a task that starts after Stop bails out at once, and one in flight has its
    headless Chrome quit."""

    def __init__(self, url: str, key=None, token=None):
        super().__init__()
        self.url = url
        self.key = key
        self.token = token
        self.signals = ScrapeSignals()

    @Slot()
    def run(self) -> None:
        set_cancel_token(self.token)
        try:
            if self.token is not None and self.token.cancelled:
                data = ProductData(url=self.url, error="Stopped by user")
            else:
                data = scrape(self.url)
        except Exception as exc:  # never let a worker thread crash the app
            data = ProductData(url=self.url, error=str(exc))
        finally:
            set_cancel_token(None)
        try:
            self.signals.finished.emit(self.key, data)
        except RuntimeError:
            # UI was torn down (app quitting) while this scrape was still running.
            pass
