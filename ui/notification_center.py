"""In-app notifications center (Phase 40): a window listing recent changes.

Receives pre-formatted rows (each a dict: when · product · change, plus the
product's url / id) and callbacks. Clicking a product opens its link; right-click
offers Graph / Delete, wired to the main window's handlers. Newest first. Columns
are user-resizable, and the window size + column widths persist across opens.
"""
from functools import partial

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core import datastore as repo
from ui.theme import link_color

_GEOMETRY_KEY = "notif_center/geometry"
_HEADER_KEY = "notif_center/header_state_v1"
_DEFAULT_WIDTHS = (140, 560, 360)  # When, Product, Change

_COL_WHEN, _COL_PRODUCT, _COL_CHANGE = range(3)
_URL_ROLE = Qt.ItemDataRole.UserRole
_PID_ROLE = Qt.ItemDataRole.UserRole + 1

# Price-direction colors for the Change cell (matches the main table convention).
_PRICE_UP_COLOR = QColor("#cc3b3b")    # price rose → red (buyer's view)
_PRICE_DOWN_COLOR = QColor("#2e9e44")  # price fell → green


class NotificationCenterDialog(QDialog):
    def __init__(self, rows, on_clear, on_open=None, on_graph=None, on_delete=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notifications")
        self._on_clear = on_clear
        self._on_open = on_open
        self._on_graph = on_graph
        self._on_delete = on_delete

        layout = QVBoxLayout(self)
        if rows:
            layout.addWidget(QLabel(
                f"{len(rows)} recent change(s), newest first — click a product to "
                "open it, right-click for graph / delete:"
            ))
        else:
            layout.addWidget(QLabel(
                "No notifications yet. Price and stock changes from each refresh "
                "will appear here."
            ))

        self.table = QTableWidget(len(rows), 3)
        self.table.setHorizontalHeaderLabels(["When", "Product", "Change"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        link = link_color()
        for r, row in enumerate(rows):
            when_item = QTableWidgetItem(row.get("when", ""))
            when_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, _COL_WHEN, when_item)

            product_item = QTableWidgetItem(row.get("product", ""))
            url = row.get("url")
            pid = row.get("product_id")
            if url:  # make it read + behave like a link
                product_item.setData(_URL_ROLE, url)
                product_item.setForeground(link)
                f = product_item.font(); f.setUnderline(True); product_item.setFont(f)
                product_item.setToolTip(f"Open: {url}")
            if pid is not None:
                product_item.setData(_PID_ROLE, pid)
            self.table.setItem(r, _COL_PRODUCT, product_item)

            change_text = row.get("change", "")
            change_item = QTableWidgetItem(change_text)
            if "▲" in change_text:      # price rose
                change_item.setForeground(_PRICE_UP_COLOR)
            elif "▼" in change_text:    # price fell
                change_item.setForeground(_PRICE_DOWN_COLOR)
            self.table.setItem(r, _COL_CHANGE, change_item)

        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_row_menu)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col, _DEFAULT_WIDTHS[col])
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.clear_button = QPushButton("Clear all")
        self.clear_button.setEnabled(bool(rows))
        self.clear_button.clicked.connect(self._clear)
        buttons.addWidget(self.clear_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._restore_state()

    # --- row interactions --------------------------------------------------

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col != _COL_PRODUCT or self._on_open is None:
            return
        item = self.table.item(row, _COL_PRODUCT)
        url = item.data(_URL_ROLE) if item else None
        if url:
            self._on_open(url)

    def _show_row_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        item = self.table.item(row, _COL_PRODUCT)
        product_id = item.data(_PID_ROLE) if item else None
        if product_id is None:  # older notifications have no product reference
            return
        menu = QMenu(self)

        # Add to a group (skip ones the product is already in) or a new group.
        current = {g.id for g in repo.groups_for_product(product_id)}
        add_menu = menu.addMenu("Add to group")
        for group in repo.list_groups():
            if group.id not in current:
                add_menu.addAction(group.name, partial(self._add_to_group, group.id, product_id))
        if add_menu.actions():
            add_menu.addSeparator()
        add_menu.addAction("New group…", partial(self._add_to_new_group, product_id))

        menu.addAction("Add to cart", partial(self._add_to_cart, product_id))
        menu.addSeparator()
        if self._on_graph is not None:
            menu.addAction("Graph", lambda: self._on_graph(product_id))
        if self._on_delete is not None:
            menu.addAction("Delete", lambda: self._on_delete(product_id))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_to_group(self, group_id, product_id) -> None:
        repo.add_to_group(group_id, product_id)

    def _add_to_new_group(self, product_id) -> None:
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if ok and name.strip():
            group = repo.create_group(name.strip())
            repo.add_to_group(group.id, product_id)

    def _add_to_cart(self, product_id) -> None:
        repo.add_to_cart(product_id)

    # --- persistence -------------------------------------------------------

    def _restore_state(self) -> None:
        settings = QSettings()
        geometry = settings.value(_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(720, 460)
        header_state = settings.value(_HEADER_KEY)
        if header_state is not None:
            self.table.horizontalHeader().restoreState(header_state)

    def _save_state(self) -> None:
        settings = QSettings()
        settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        settings.setValue(_HEADER_KEY, self.table.horizontalHeader().saveState())

    def done(self, result) -> None:
        self._save_state()
        super().done(result)

    # --- actions -----------------------------------------------------------

    def _clear(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear notifications", "Remove all notifications from the list?"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._on_clear()
            self.accept()
