"""Shopping cart (Phase 38): tracked products + quantities with a live total.

Cart items reference tracked products, so a price change from any refresh flows
straight into the line totals and the grand total the next time the cart opens.
Quantities are editable inline and persist immediately.
"""
from functools import partial

from PySide6.QtCore import QPoint, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import datastore as repo
from core.currency import normalize_currency
from ui.change_cell import add_period_actions, change_header, change_item
from ui.formatting import format_price
from ui.logos import _domain_key, logo_pixmap
from ui.theme import STOP_BUTTON_QSS, link_color

(_COL_LOGO, _COL_NAME, _COL_SITE, _COL_PRICE, _COL_CHANGE, _COL_QTY, _COL_TOTAL,
 _COL_REFRESH, _COL_GRAPH, _COL_EDIT, _COL_REMOVE, _COL_DELETE) = range(12)
_UP_COLOR = "#cc3b3b"    # price rose (buyer's view)
_DOWN_COLOR = "#2e9e44"  # price fell


def _site_name(url: str) -> str:
    return _domain_key(url).capitalize()


class CartDialog(QDialog):
    def __init__(self, parent=None, on_changed=None, on_refresh=None, on_edit=None,
                 on_refresh_many=None, on_stop=None, on_graph=None, on_period=None):
        super().__init__(parent)
        self._on_changed = on_changed  # called after a delete so the caller refreshes
        self._on_refresh = on_refresh  # re-scrape one product (main window handler)
        self._on_edit = on_edit        # edit name / URL / target (main window handler)
        self._on_refresh_many = on_refresh_many  # refresh a list of products as one batch
        self._on_stop = on_stop        # stop the running refresh (main window)
        self._on_graph = on_graph      # open a product's price graph (main window)
        self._on_period = on_period    # change the Change column's period (main window)
        self._refreshing = False       # pushed by the main window (set_refresh_state)
        self.products = []
        self.setWindowTitle("Shopping cart")
        self.resize(1270, 560)
        layout = QVBoxLayout(self)

        self._intro = QLabel()
        self._intro.setWordWrap(True)
        self._intro.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._intro)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(
            ["", "Product", "Site", "Unit price", self._change_header_text(), "Qty", "Line total", "", "", "", "", ""]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setDefaultSectionSize(46)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(_COL_LOGO, 76)
        self.table.setColumnWidth(_COL_SITE, 110)
        self.table.setColumnWidth(_COL_PRICE, 120)
        self.table.setColumnWidth(_COL_CHANGE, 90)
        self.table.setColumnWidth(_COL_QTY, 80)
        self.table.setColumnWidth(_COL_TOTAL, 130)
        self.table.setColumnWidth(_COL_REFRESH, 90)
        self.table.setColumnWidth(_COL_GRAPH, 90)
        self.table.setColumnWidth(_COL_EDIT, 90)
        self.table.setColumnWidth(_COL_REMOVE, 90)
        self.table.setColumnWidth(_COL_DELETE, 90)
        self.table.cellClicked.connect(self._open_link)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.total_label = QLabel()
        self.total_label.setTextFormat(Qt.TextFormat.RichText)
        font = self.total_label.font(); font.setPointSize(font.pointSize() + 2)
        self.total_label.setFont(font)
        bottom.addWidget(self.total_label, 1)
        self.refresh_button = QPushButton()
        self.refresh_button.setObjectName("primary")
        self.refresh_button.clicked.connect(self._on_refresh_button)
        self.refresh_button.setVisible(on_refresh_many is not None)
        bottom.addWidget(self.refresh_button)
        self.clear_button = QPushButton("Clear cart")
        self.clear_button.clicked.connect(self._clear)
        bottom.addWidget(self.clear_button)
        layout.addLayout(bottom)

        self._reload()

    # --- data --------------------------------------------------------------

    def reload_prices(self) -> None:
        """Public hook: re-pull from the store after a refresh so prices/totals
        update live while the cart is open. Quantities persist, so they survive."""
        self._reload()

    def _reload(self) -> None:
        self.products = repo.cart_products()
        self._by_id = {p.id: p for p in self.products}
        self._qty = {p.id: (getattr(p, "quantity", 1) or 1) for p in self.products}
        self._total_items = {}
        # Some products are scraped without a currency label (empty string) even
        # though they're priced in the same currency as the rest. If exactly one
        # real currency is present, treat the unlabeled ones as that currency so
        # the cart shows a single combined total instead of a phantom second one.
        known = {normalize_currency(p.currency) for p in self.products
                 if p.last_price is not None and normalize_currency(p.currency)}
        self._default_cur = next(iter(known)) if len(known) == 1 else ""

        self.table.setRowCount(0)
        for product in self.products:
            self._add_row(product)

        if self.products:
            self._intro.setText(
                f"<b>{len(self.products)}</b> item(s) in your cart. Change quantities "
                "below — the total updates live and tracks future price changes."
            )
        else:
            self._intro.setText(
                "Your cart is empty. Right-click a product in the main list → "
                "<b>Add to cart</b> to start building one."
            )
        self.clear_button.setEnabled(bool(self.products))
        self.set_refresh_state(self._refreshing)  # enable/disable for an empty cart
        self._update_total()

    def _add_row(self, product) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = logo_pixmap(product, 64, 30)
        if pm is not None:
            logo.setPixmap(pm)
        self.table.setCellWidget(row, _COL_LOGO, logo)

        name_item = QTableWidgetItem(product.name or product.url)
        name_item.setData(Qt.ItemDataRole.UserRole, product.url)
        name_item.setForeground(link_color())
        f = name_item.font(); f.setUnderline(True); name_item.setFont(f)
        name_item.setToolTip(f"Open: {product.url}")
        self.table.setItem(row, _COL_NAME, name_item)

        site_item = QTableWidgetItem(_site_name(product.url))
        site_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, _COL_SITE, site_item)

        price_item = QTableWidgetItem(format_price(product.last_price, self._cur(product)))
        price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, _COL_PRICE, price_item)
        self.table.setItem(row, _COL_CHANGE, change_item(product))

        spin = QSpinBox()
        spin.setRange(1, 999)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setValue(self._qty[product.id])
        spin.valueChanged.connect(partial(self._on_qty_changed, product.id))
        self.table.setCellWidget(row, _COL_QTY, spin)

        total_item = QTableWidgetItem(self._line_total_text(product, self._qty[product.id]))
        total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, _COL_TOTAL, total_item)
        self._total_items[product.id] = total_item

        refresh = QPushButton("Refresh")
        refresh.setToolTip("Re-check this product's price / stock now")
        refresh.clicked.connect(partial(self._refresh, product.id))
        self.table.setCellWidget(row, _COL_REFRESH, refresh)

        graph = QPushButton("Graph")
        graph.setToolTip("Show this product's price history")
        graph.clicked.connect(partial(self._graph, product.id))
        graph.setEnabled(self._on_graph is not None)
        self.table.setCellWidget(row, _COL_GRAPH, graph)

        edit = QPushButton("Edit")
        edit.setToolTip("Edit the product's name, link, or target price")
        edit.clicked.connect(partial(self._edit, product.id))
        edit.setEnabled(self._on_edit is not None)
        self.table.setCellWidget(row, _COL_EDIT, edit)

        remove = QPushButton("Remove")
        remove.setToolTip("Remove from the cart (keeps tracking the product)")
        remove.clicked.connect(partial(self._remove, product.id))
        self.table.setCellWidget(row, _COL_REMOVE, remove)

        delete = QPushButton("Delete")
        delete.setToolTip("Delete the product from your list (and the cart)")
        delete.clicked.connect(partial(self._delete, product))
        self.table.setCellWidget(row, _COL_DELETE, delete)

    def _cur(self, product) -> str:
        """The product's normalized currency, falling back to the cart's single
        known currency when this product was scraped without a label."""
        return normalize_currency(product.currency) or self._default_cur

    def _line_total_text(self, product, qty: int) -> str:
        if product.last_price is None:
            return "N/A"
        return format_price(product.last_price * qty, self._cur(product))

    def _update_total(self) -> None:
        """Sum line totals per currency (products can be priced differently), with
        a delta reflecting the most recent refresh's price changes."""
        totals, deltas = {}, {}
        for product in self.products:
            if product.last_price is None:
                continue
            qty = self._qty.get(product.id, 1)
            cur = self._cur(product)
            totals[cur] = totals.get(cur, 0.0) + product.last_price * qty
            if getattr(product, "price_changed", False) and product.prev_price is not None:
                deltas[cur] = deltas.get(cur, 0.0) + (product.last_price - product.prev_price) * qty

        if not totals:
            self.total_label.setText("<b>Total:</b> —")
            return
        parts = []
        for cur, amount in totals.items():
            text = f"<b>Total:</b> {format_price(amount, cur)}"
            delta = deltas.get(cur, 0.0)
            if abs(delta) >= 0.005:
                color = _UP_COLOR if delta > 0 else _DOWN_COLOR
                arrow = "▲" if delta > 0 else "▼"
                text += (f" &nbsp;<span style='color:{color}'>"
                         f"{arrow} {delta:+,.2f} {cur}</span>".rstrip())
            parts.append(text)
        self.total_label.setText("<br>".join(parts))

    # --- refresh the whole cart --------------------------------------------

    def set_refresh_state(self, refreshing: bool, progress: str = "") -> None:
        """Called by the main window whenever a refresh starts / progresses / ends:
        Refresh cart becomes a red Stop (with progress) while anything refreshes."""
        self._refreshing = refreshing
        button = self.refresh_button
        if refreshing:
            button.setText(f"Stop  ({progress})" if progress else "Stop")
            button.setToolTip("Stop the refresh (results already fetched are kept)")
            button.setStyleSheet(STOP_BUTTON_QSS)
            button.setEnabled(True)
        else:
            button.setText("Refresh cart")
            button.setToolTip("Re-check every product in the cart now")
            button.setStyleSheet("")
            button.setEnabled(bool(self.products))

    def _on_refresh_button(self) -> None:
        if self._refreshing:
            if self._on_stop is not None:
                self._on_stop()
        elif self.products and self._on_refresh_many is not None:
            self._on_refresh_many([p.id for p in self.products])

    # --- actions -----------------------------------------------------------

    def _on_qty_changed(self, product_id, value) -> None:
        self._qty[product_id] = value
        repo.set_cart_quantity(product_id, value)
        product = self._by_id.get(product_id)
        item = self._total_items.get(product_id)
        if product is not None and item is not None:
            item.setText(self._line_total_text(product, value))
        self._update_total()

    def _refresh(self, product_id) -> None:
        """Re-scrape one product via the main window; when it finishes, the main
        window reloads the open cart (reload_prices) so the price updates here."""
        if self._on_refresh is not None:
            self._on_refresh(product_id)

    def _graph(self, product_id) -> None:
        """Open the product's price graph on top of the cart."""
        if self._on_graph is not None:
            self._on_graph(product_id, parent=self)

    def _edit(self, product_id) -> None:
        """Open the main window's edit dialog over the cart, then rebuild so a
        changed name / link shows here right away."""
        if self._on_edit is None:
            return
        self._on_edit(product_id, parent=self)
        self._reload()

    def _remove(self, product_id) -> None:
        repo.remove_from_cart(product_id)
        self._reload()

    def _delete(self, product) -> None:
        """Delete the product from the user's list (soft delete) and the cart."""
        confirm = QMessageBox.question(
            self, "Delete product",
            f"Remove '{product.name or product.url}' from your list?\n\n"
            "It's removed from the cart too. Its price history is kept — re-adding "
            "the same link later restores it.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        repo.remove_from_cart(product.id)  # drop cart membership
        repo.delete_product(product.id)    # soft-delete from the main list
        if self._on_changed is not None:
            self._on_changed()  # let the main window refresh its table
        self._reload()

    def _clear(self) -> None:
        if not self.products:
            return
        confirm = QMessageBox.question(
            self, "Clear cart",
            "Remove all items from the cart? The products themselves stay tracked.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            repo.clear_cart()
            self._reload()

    # --- Change period (shared with the main table and group view) ------------

    def _change_header_text(self) -> str:
        # ▾ hints that clicking opens the period menu (only when it can)
        return f"{change_header()} ▾" if self._on_period is not None else change_header()

    def _on_header_clicked(self, col: int) -> None:
        if col != _COL_CHANGE or self._on_period is None:
            return
        menu = QMenu(self)
        add_period_actions(menu, self._set_period)
        header = self.table.horizontalHeader()
        pos = QPoint(header.sectionViewportPosition(_COL_CHANGE), header.height())
        menu.exec(header.mapToGlobal(pos))

    def _set_period(self, key: str) -> None:
        """The main window applies it everywhere (saved, main table + groups
        follow); then refresh this header and the rows (quantities persist)."""
        self._on_period(key)
        header_item = self.table.horizontalHeaderItem(_COL_CHANGE)
        if header_item is not None:
            header_item.setText(self._change_header_text())
        self._reload()

    def _open_link(self, row: int, col: int) -> None:
        if col != _COL_NAME:
            return
        item = self.table.item(row, _COL_NAME)
        url = item.data(Qt.ItemDataRole.UserRole) if item else None
        if url:
            QDesktopServices.openUrl(QUrl(url))
