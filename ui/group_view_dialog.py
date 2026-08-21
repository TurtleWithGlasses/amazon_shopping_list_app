"""Group comparison view (Phase 34): members side by side + combined price graph."""
from datetime import datetime, timedelta, timezone
from functools import partial

import pyqtgraph as pg
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import datastore as repo
from ui.formatting import format_price
from ui.graph_style import LINE_COLORS, style_plot
from ui.logos import _domain_key, logo_pixmap
from ui.theme import link_color

_CHEAPEST = QColor("#2e9e44")  # green: the lowest-priced member

# columns
_COL_SWATCH, _COL_LOGO, _COL_NAME, _COL_SITE, _COL_PRICE, _COL_LOW = range(6)


def _site_name(url: str) -> str:
    return _domain_key(url).capitalize()


class GroupViewDialog(QDialog):
    def __init__(self, group_id: int, group_name: str, parent=None, on_changed=None,
                 on_refresh=None):
        super().__init__(parent)
        self.group_id = group_id
        self.group_name = group_name
        self._on_changed = on_changed  # called after a delete so the caller refreshes
        self._on_refresh = on_refresh  # re-scrape one product (main window handler)
        self.setWindowTitle(f"Group — {group_name}")
        self.resize(860, 680)
        self._layout = QVBoxLayout(self)
        self._populate()

    def reload_view(self) -> None:
        """Public hook: rebuild the table + graph (e.g. after a refresh lands)."""
        self._populate()

    def _populate(self) -> None:
        """(Re)build the members table + graph from the current group membership.
        Called on open and again after a product is deleted from the group."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        members = repo.group_members(self.group_id)
        # Cheapest first (products without a price sort to the bottom).
        members.sort(key=lambda m: (m.last_price is None, m.last_price or 0.0))
        self.members = members
        # One color per member (in this sorted order) — shared by the row swatch
        # and the graph line so they're easy to match.
        self._colors = {m.id: LINE_COLORS[i % len(LINE_COLORS)]
                        for i, m in enumerate(members)}
        priced = [m for m in members if m.last_price is not None]
        self._cheapest_id = priced[0].id if priced else None

        if not members:
            self._layout.addWidget(QLabel("This group has no products yet."))
            return

        self._layout.addWidget(QLabel(
            f"<b>{self.group_name}</b> — {len(members)} product(s); cheapest first, "
            "highlighted in green. Click a name to open it; right-click to move or delete."
        ))

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_graph())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([230, 380])
        self._layout.addWidget(splitter, 1)

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
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_row_menu)

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

    # --- delete a product from the group + main list -----------------------

    def _show_row_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self.members):  # rows are in self.members order
            return
        product = self.members[row]
        menu = QMenu(self)

        # Move to another group (or a new one).
        move_menu = menu.addMenu("Move to group")
        others = [g for g in repo.list_groups() if g.id != self.group_id]
        for group in others:
            move_menu.addAction(group.name, partial(self._move, product, group.id))
        if others:
            move_menu.addSeparator()
        move_menu.addAction("New group…", partial(self._move_to_new, product))

        menu.addAction("Remove from group", partial(self._remove_from_group, product))
        menu.addAction("Add to cart", partial(self._add_to_cart, product))
        if self._on_refresh is not None:
            menu.addAction("Refresh", partial(self._refresh, product))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete(product))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _refresh(self, product) -> None:
        """Re-scrape one product via the main window; when it finishes, the main
        window rebuilds this view (reload_view) so the new price shows here."""
        self._on_refresh(product.id)

    def _remove_from_group(self, product) -> None:
        """Take the product out of this group only (it stays tracked, in the main
        list, in any other groups, and in the cart)."""
        repo.remove_from_group(self.group_id, product.id)
        self._populate()  # rebuild without the product

    def _add_to_cart(self, product) -> None:
        """Add the product to the shopping cart immediately (no-op if already in)."""
        repo.add_to_cart(product.id)

    def _move(self, product, target_group_id) -> None:
        """Move a product out of this group and into another (the product stays
        tracked; only its group membership changes)."""
        repo.remove_from_group(self.group_id, product.id)
        repo.add_to_group(target_group_id, product.id)  # no-op if already a member
        self._populate()  # this group loses the product; the main list is unchanged

    def _move_to_new(self, product) -> None:
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if ok and name.strip():
            group = repo.create_group(name.strip())
            self._move(product, group.id)

    def _delete(self, product) -> None:
        confirm = QMessageBox.question(
            self, "Delete product",
            f"Remove '{product.name or product.url}' from this group and your list?\n\n"
            "Its price history is kept — re-adding the same link later restores it.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        repo.remove_from_group(self.group_id, product.id)  # drop group membership
        repo.delete_product(product.id)                    # soft-delete from the list
        if self._on_changed is not None:
            self._on_changed()   # let the main window refresh its table
        self._populate()         # rebuild this view without the product

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
        t = style_plot(plot)
        plot.setLabel("left", "Price", color=t["subtext"])
        plot.addLegend(offset=(10, 10), labelTextColor=t["text"])

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
                brush=pg.mkBrush(color), pen=pg.mkPen(t["base"], width=0.5),
                hoverable=True, hoverSize=12, hoverPen=pg.mkPen(t["text"], width=1),
                data=tips, tip=lambda x, y, data: data,
            )
            plot.addItem(scatter)
            plotted = True

        if plotted:
            return plot
        return QLabel("No price history to chart yet.")
