"""Background startup load, so the main window shows immediately.

The products are fetched first (one quick request) and handed to the GUI so the
table can render; the slower extras — trend history, the Change column's past
prices, first prices, group names — follow in a second signal. Everything runs
on a worker thread; the GUI only receives plain data through queued signals.
"""
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core import datastore as repo
from services.trend import price_trend
from ui.change_cell import period_cutoffs

TREND_DAYS = 7  # same window as MainWindow._recompute_trends


class _Signals(QObject):
    products = Signal(object)  # list of products
    extras = Signal(object)    # dict: trend_cache / period_prices / first_prices /
                               #       group_names / groups
    failed = Signal(str)       # the product list couldn't be loaded


class StartupLoadTask(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _Signals()

    def _emit(self, signal, value) -> None:
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # the window was closed (e.g. logout) before the load finished

    @Slot()
    def run(self) -> None:
        try:
            products = repo.list_products()
        except Exception as exc:
            self._emit(self.signals.failed, str(exc))
            return
        self._emit(self.signals.products, products)

        # Each extra is independent: one failing leaves that column at its default
        # (it fills in after the next refresh) instead of blocking the rest.
        now = datetime.now(timezone.utc)
        extras = {}
        try:
            history = repo.recent_history(now - timedelta(days=TREND_DAYS))
            extras["trend_cache"] = {pid: price_trend(points) for pid, points in history.items()}
        except Exception:
            pass
        try:
            extras["period_prices"] = repo.prices_at(period_cutoffs(now))
        except Exception:
            pass
        try:
            extras["first_prices"] = repo.first_prices()
        except Exception:
            pass
        try:
            extras["group_names"] = repo.group_names_by_product()
        except Exception:
            pass
        try:
            extras["groups"] = [(g.id, g.name) for g in repo.list_groups()]
        except Exception:
            pass
        self._emit(self.signals.extras, extras)
