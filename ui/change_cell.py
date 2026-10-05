"""The "Change" cell: percentage of the product's last price move.

Shared by the main table, the group view and the cart so all three show the
same value. Computed from data every product row already carries
(`prev_price` → `last_price`), so it costs one division per row and no queries.
`prev_price` is only updated when the price actually changes, so the cell keeps
showing the most recent move until the price moves again.
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from ui.formatting import format_price

_UP = QColor("#cc3b3b")      # price rose (buyer's view) — matches the ▲ elsewhere
_DOWN = QColor("#2e9e44")    # price fell
_NONE = QColor("#888888")    # no change recorded yet


def price_change_pct(product) -> Optional[float]:
    """% change from the previous price to the current one, or None."""
    prev = getattr(product, "prev_price", None)
    last = getattr(product, "last_price", None)
    if prev is None or last is None or prev <= 0 or prev == last:
        return None
    return (last - prev) / prev * 100.0


def change_item(product) -> QTableWidgetItem:
    """A centered, colored table item like '▼ -7.7%' (or '—' if no change yet).
    The raw percentage is stored as UserRole data for sorting."""
    pct = price_change_pct(product)
    if pct is None:
        item = QTableWidgetItem("—")
        item.setForeground(_NONE)
        item.setToolTip("No price change recorded yet")
    else:
        arrow = "▲" if pct > 0 else "▼"
        item = QTableWidgetItem(f"{arrow} {pct:+.1f}%")
        item.setForeground(_UP if pct > 0 else _DOWN)
        cur = getattr(product, "currency", "") or ""
        item.setToolTip(
            f"Last change: {format_price(product.prev_price, cur)} → "
            f"{format_price(product.last_price, cur)}"
        )
        item.setData(Qt.ItemDataRole.UserRole, pct)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item
