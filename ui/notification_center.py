"""In-app notifications center (Phase 40): a window listing recent changes.

Receives pre-formatted rows (each a dict: when · product · change, plus the
product's url / id) and callbacks. Clicking a product opens its link; right-click
offers Graph / Delete, wired to the main window's handlers. Newest first. Columns
are user-resizable, and the window size + column widths persist across opens.
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.theme import link_color

_GEOMETRY_KEY = "notif_center/geometry"
_HEADER_KEY = "notif_center/header_state_v1"
_DEFAULT_WIDTHS = (140, 560, 360)  # When, Product, Change

_COL_WHEN, _COL_PRODUCT, _COL_CHANGE = range(3)
_URL_ROLE = Qt.ItemDataRole.UserRole
_PID_ROLE = Qt.ItemDataRole.UserRole + 1


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

            self.table.setItem(r, _COL_CHANGE, QTableWidgetItem(row.get("change", "")))

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
        if self._on_graph is not None:
            menu.addAction("Graph", lambda: self._on_graph(product_id))
        if self._on_delete is not None:
            menu.addAction("Delete", lambda: self._on_delete(product_id))
        if menu.actions():
            menu.exec(self.table.viewport().mapToGlobal(pos))

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
