"""Shopping cart (Phase 38): tracked products + quantities with a live total.

Cart items reference tracked products, so a price change from any refresh flows
straight into the line totals and the grand total the next time the cart opens.
Quantities are editable inline and persist immediately.
"""
from functools import partial

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import datastore as repo
from ui.formatting import format_price
from ui.logos import _domain_key, logo_pixmap
from ui.theme import link_color

_COL_LOGO, _COL_NAME, _COL_SITE, _COL_PRICE, _COL_QTY, _COL_TOTAL, _COL_REMOVE = range(7)
_UP_COLOR = "#cc3b3b"    # price rose (buyer's view)
_DOWN_COLOR = "#2e9e44"  # price fell


def _site_name(url: str) -> str:
    return _domain_key(url).capitalize()


class CartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shopping cart")
        self.resize(840, 560)
        layout = QVBoxLayout(self)

        self._intro = QLabel()
        self._intro.setWordWrap(True)
        self._intro.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._intro)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["", "Product", "Site", "Unit price", "Qty", "Line total", ""]
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
        self.table.setColumnWidth(_COL_QTY, 80)
        self.table.setColumnWidth(_COL_TOTAL, 130)
        self.table.setColumnWidth(_COL_REMOVE, 90)
        self.table.cellClicked.connect(self._open_link)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.total_label = QLabel()
        self.total_label.setTextFormat(Qt.TextFormat.RichText)
        font = self.total_label.font(); font.setPointSize(font.pointSize() + 2)
        self.total_label.setFont(font)
        bottom.addWidget(self.total_label, 1)
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
        known = {(p.currency or "").strip() for p in self.products
                 if p.last_price is not None and (p.currency or "").strip()}
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

        remove = QPushButton("Remove")
        remove.clicked.connect(partial(self._remove, product.id))
        self.table.setCellWidget(row, _COL_REMOVE, remove)

    def _cur(self, product) -> str:
        """The product's currency, falling back to the cart's single known
        currency when this product was scraped without a label."""
        return (product.currency or "").strip() or self._default_cur

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

    # --- actions -----------------------------------------------------------

    def _on_qty_changed(self, product_id, value) -> None:
        self._qty[product_id] = value
        repo.set_cart_quantity(product_id, value)
        product = self._by_id.get(product_id)
        item = self._total_items.get(product_id)
        if product is not None and item is not None:
            item.setText(self._line_total_text(product, value))
        self._update_total()

    def _remove(self, product_id) -> None:
        repo.remove_from_cart(product_id)
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

    def _open_link(self, row: int, col: int) -> None:
        if col != _COL_NAME:
            return
        item = self.table.item(row, _COL_NAME)
        url = item.data(Qt.ItemDataRole.UserRole) if item else None
        if url:
            QDesktopServices.openUrl(QUrl(url))
