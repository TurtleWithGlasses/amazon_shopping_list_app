"""The "Change" cell: percentage price change over a selectable period.

Shared by the main table, the group view and the cart so all three show the
same value. The period ("Last" change, 1W, 1M, 3M, 6M, 1Y) is chosen from the
main table's Change header and held here as module state.

- "Last" compares `prev_price` → `last_price` (already on every row; no query).
  `prev_price` only moves when the price changes, so it shows the most recent move.
- The other periods compare the current price with the price N days ago. Those
  base prices come from one batched query (`repo.prices_at`) run at startup and
  after each batch refresh, cached here — so switching periods, sorting and
  rebuilding tables never hit the database.
"""
from datetime import datetime, timedelta
from functools import partial
from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from ui.formatting import format_price

_UP = QColor("#cc3b3b")      # price rose (buyer's view) — matches the ▲ elsewhere
_DOWN = QColor("#2e9e44")    # price fell
_NONE = QColor("#888888")    # no change / no data

# (key, menu label, short header tag, days back)
PERIODS = (
    ("last", "Last change", "", None),
    ("1w", "1 week", "1W", 7),
    ("1m", "1 month", "1M", 30),
    ("3m", "3 months", "3M", 91),
    ("6m", "6 months", "6M", 182),
    ("1y", "1 year", "1Y", 365),
)
_BY_KEY = {key: (label, tag, days) for key, label, tag, days in PERIODS}
DEFAULT_PERIOD = "last"

_period = DEFAULT_PERIOD
_base_prices: Dict[str, Dict[int, float]] = {}  # period key -> {product_id: price then}


def current_period() -> str:
    return _period


def set_period(key: str) -> None:
    global _period
    _period = key if key in _BY_KEY else DEFAULT_PERIOD


def set_base_prices(prices: Dict[str, Dict[int, float]]) -> None:
    """Replace the cached 'price N days ago' map (from `repo.prices_at`)."""
    global _base_prices
    _base_prices = prices or {}


def period_cutoffs(now: datetime) -> Dict[str, datetime]:
    """The moment each historical period looks back to, e.g. {'1w': now-7d, …}."""
    return {key: now - timedelta(days=days) for key, _l, _t, days in PERIODS if days}


def change_header() -> str:
    """Column title for the selected period: 'Change' or e.g. 'Change (1M)'."""
    tag = _BY_KEY[_period][1]
    return f"Change ({tag})" if tag else "Change"


def add_period_actions(menu, on_select: Callable[[str], None]) -> None:
    """Add the checkable period choices (Last change … 1 year) to a QMenu, the
    selected one ticked. Used by the main table and the group view headers."""
    for key, label, _tag, _days in PERIODS:
        action = menu.addAction(label, partial(on_select, key))
        action.setCheckable(True)
        action.setChecked(key == _period)


def period_label(key: Optional[str] = None) -> str:
    return _BY_KEY[key or _period][0]


def _base_price(product) -> Optional[float]:
    if _period == "last":
        return getattr(product, "prev_price", None)
    return _base_prices.get(_period, {}).get(product.id)


def price_change_pct(product) -> Optional[float]:
    """% change over the selected period, or None when there's nothing to compare.
    For 'Last', an unchanged price is None (no move recorded); for a time period
    it's 0.0 (the price was the same N days ago)."""
    base = _base_price(product)
    last = getattr(product, "last_price", None)
    if base is None or last is None or base <= 0:
        return None
    if _period == "last" and base == last:
        return None
    return (last - base) / base * 100.0


def change_item(product) -> QTableWidgetItem:
    """A centered, colored table item like '▼ -7.7%' ('0.0%' / '—' when flat or
    unknown). The raw percentage is stored as UserRole data."""
    pct = price_change_pct(product)
    cur = getattr(product, "currency", "") or ""
    if pct is None:
        item = QTableWidgetItem("—")
        item.setForeground(_NONE)
        item.setToolTip(
            "No price change recorded yet" if _period == "last"
            else f"No price history from {period_label()} ago yet"
        )
    else:
        if abs(pct) < 0.05:
            item = QTableWidgetItem("0.0%")
            item.setForeground(_NONE)
        else:
            arrow = "▲" if pct > 0 else "▼"
            item = QTableWidgetItem(f"{arrow} {pct:+.1f}%")
            item.setForeground(_UP if pct > 0 else _DOWN)
        base = _base_price(product)
        if _period == "last":
            tip = f"Last change: {format_price(base, cur)} → {format_price(product.last_price, cur)}"
        else:
            tip = (f"{period_label()} ago: {format_price(base, cur)} → "
                   f"now: {format_price(product.last_price, cur)}")
        item.setToolTip(tip)
        item.setData(Qt.ItemDataRole.UserRole, pct)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item
