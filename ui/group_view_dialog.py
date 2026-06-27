"""Group comparison view (Phase 34): members side by side + combined price graph."""
from datetime import datetime, timedelta, timezone

import pyqtgraph as pg
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import datastore as repo
from ui.formatting import format_price
from ui.logos import _domain_key, logo_pixmap
from ui.theme import link_color

_LINE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd",
                "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]
_CHEAPEST = QColor("#2e9e44")  # green: the lowest-priced member

# columns
_COL_SWATCH, _COL_LOGO, _COL_NAME, _COL_SITE, _COL_PRICE, _COL_LOW = range(6)


def _site_name(url: str) -> str:
    return _domain_key(url).capitalize()


class GroupViewDialog(QDialog):
    def __init__(self, group_id: int, group_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Group — {group_name}")
        self.resize(860, 680)
        layout = QVBoxLayout(self)

        members = repo.group_members(group_id)
        # Cheapest first (products without a price sort to the bottom).
        members.sort(key=lambda m: (m.last_price is None, m.last_price or 0.0))
        self.members = members
        # One color per member (in this sorted order) — shared by the row swatch
        # and the graph line so they're easy to match.
        self._colors = {m.id: _LINE_COLORS[i % len(_LINE_COLORS)]
                        for i, m in enumerate(members)}
        priced = [m for m in members if m.last_price is not None]
        self._cheapest_id = priced[0].id if priced else None

        if not members:
            layout.addWidget(QLabel("This group has no products yet."))
            return

        layout.addWidget(QLabel(
            f"<b>{group_name}</b> — {len(members)} product(s); cheapest first, "
            "highlighted in green. Click a name to open it."
        ))

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_graph())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([230, 380])
        layout.addWidget(splitter, 1)

    # --- members table -----------------------------------------------------

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, 6)
        self.table = table
        table.setHorizontalHeaderLabels(["", "", "Product", "Site", "Price", "30-day low"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setDefaultSectionSize(44)
        header = table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(_COL_SWATCH, 20)
        table.setColumnWidth(_COL_LOGO, 76)
        table.setColumnWidth(_COL_SITE, 110)
        table.setColumnWidth(_COL_PRICE, 130)
        table.setColumnWidth(_COL_LOW, 130)
        table.cellClicked.connect(self._open_link)

        since30 = datetime.now(timezone.utc) - timedelta(days=30)
        for product in self.members:
            row = table.rowCount()
            table.insertRow(row)
            cheapest = product.id == self._cheapest_id

            swatch = QTableWidgetItem()
            swatch.setBackground(QColor(self._colors[product.id]))  # matches graph line
            table.setItem(row, _COL_SWATCH, swatch)

            logo = QLabel()
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pm = logo_pixmap(product, 64, 30)
            if pm is not None:
                logo.setPixmap(pm)
            table.setCellWidget(row, _COL_LOGO, logo)

            name_item = QTableWidgetItem(("⭐ " if cheapest else "") + (product.name or product.url))
            name_item.setData(Qt.ItemDataRole.UserRole, product.url)
            name_item.setForeground(link_color())
            font = name_item.font(); font.setUnderline(True); name_item.setFont(font)
            name_item.setToolTip(f"Open: {product.url}")
            table.setItem(row, _COL_NAME, name_item)

            table.setItem(row, _COL_SITE, QTableWidgetItem(_site_name(product.url)))

            price_item = QTableWidgetItem(format_price(product.last_price, product.currency))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if cheapest:
                price_item.setForeground(_CHEAPEST)
                f = price_item.font(); f.setBold(True); price_item.setFont(f)
            table.setItem(row, _COL_PRICE, price_item)

            low = self._thirty_day_low(product.id, since30)
            low_item = QTableWidgetItem(format_price(low, product.currency) if low is not None else "—")
            low_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, _COL_LOW, low_item)
        return table

    def _open_link(self, row: int, col: int) -> None:
        if col != _COL_NAME:
            return
        item = self.table.item(row, _COL_NAME)
        url = item.data(Qt.ItemDataRole.UserRole) if item else None
        if url:
            QDesktopServices.openUrl(QUrl(url))

    @staticmethod
    def _thirty_day_low(product_id, since):
        prices = [h.price for h in repo.get_price_history(product_id, since=since) if h.price is not None]
        return min(prices) if prices else None

    # --- combined graph ----------------------------------------------------

    @staticmethod
    def _fmt_time(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")

    def _build_graph(self):
        axis = pg.DateAxisItem(orientation="bottom")
        plot = pg.PlotWidget(axisItems={"bottom": axis})
        plot.setBackground("w")
        plot.setLabel("left", "Price")
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.addLegend(offset=(10, 10))

        plotted = False
        for product in self.members:
            points = [(h.captured_at.replace(tzinfo=timezone.utc).timestamp(), h.price)
                      for h in repo.get_price_history(product.id) if h.price is not None]
            if not points:
                continue
            xs = [t for t, _ in points]
            ys = [p for _, p in points]
            color = self._colors[product.id]
            site = _site_name(product.url)  # which store this line belongs to
            plot.plot(xs, ys, pen=pg.mkPen(color, width=2),
                      name=f"{site} · {(product.name or product.url)[:28]}")
            # Hoverable points so the user can read site + product + price + time.
            cur = product.currency or ""
            name = (product.name or product.url)[:40]
            tips = [f"{site}\n{name}\n{format_price(p, cur)}\n{self._fmt_time(t)}"
                    for t, p in points]
            scatter = pg.ScatterPlotItem(
                x=xs, y=ys, size=6,
                brush=pg.mkBrush(color), pen=pg.mkPen("w", width=0.5),
                hoverable=True, hoverSize=12, hoverPen=pg.mkPen("k", width=1),
                data=tips, tip=lambda x, y, data: data,
            )
            plot.addItem(scatter)
            plotted = True

        if plotted:
            return plot
        return QLabel("No price history to chart yet.")
