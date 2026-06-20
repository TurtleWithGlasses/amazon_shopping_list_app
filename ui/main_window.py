"""Main application window: product table, add/refresh, edit/delete, graph, export."""
import os
from functools import partial

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import datastore as repo
from core.cloud import auth
from services import export as export_service
from services.scrape_worker import ScrapeTask
from services.timescales import DEFAULT_TIMESCALE, TIMESCALE_LABELS
from ui.edit_dialog import EditProductDialog
from ui.graph_dialog import GraphDialog
from ui.icons import app_icon
from ui.image_cache import ImageLoader
from ui.settings_dialog import SettingsDialog

_PREFIX_SYMBOLS = {"$", "€", "£", "¥", "₺", "₹"}
_CHANGED_COLOR = QColor("#e8830c")  # orange for changed price/stock

COL_MOVE, COL_IMAGE, COL_NAME, COL_PRICE, COL_STOCK, COL_CHECKED, COL_ACTIONS = range(7)
IMG_SIZE = 56    # product thumbnail size (px)
ROW_HEIGHT = 70  # row height; leaves margin around the thumbnail

# Timer intervals (overridable via env vars for testing).
REFRESH_INTERVAL_MS = int(os.environ.get("PRICETRACKER_REFRESH_MS", 5 * 60 * 1000))      # 5 min
SNAPSHOT_INTERVAL_MS = int(os.environ.get("PRICETRACKER_SNAPSHOT_MS", 60 * 60 * 1000))   # 1 hour


def format_price(price, currency: str) -> str:
    if price is None:
        return "N/A"
    formatted = f"{price:,.2f}"
    if currency in _PREFIX_SYMBOLS:
        return f"{currency}{formatted}"
    return f"{formatted} {currency}" if currency else formatted


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Price Tracker")
        self.resize(1000, 600)
        self._pool = QThreadPool.globalInstance()
        self._tasks = []          # keep refs so QRunnables aren't GC'd
        self._pending_refresh = 0
        self._really_quit = False
        self.logout_requested = False
        self._tray_available = False
        self.tray_icon = None
        # per-batch refresh state
        self._refresh_snapshot = False
        self._refresh_notify = False
        self._refresh_changes = []
        # Sort state: column None = manual (position) order.
        self._sort_column = None
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._settings = QSettings()
        self._images = ImageLoader(self)

        self._build_menu()
        self._build_central()
        self._build_tray()
        self._restore_layout()
        self.reload()
        self._start_timers()

    # --- construction ------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        export_csv = QAction("Export to &CSV…", self)
        export_csv.triggered.connect(partial(self._export, "csv"))
        file_menu.addAction(export_csv)

        export_xlsx = QAction("Export to &Excel…", self)
        export_xlsx.triggered.connect(partial(self._export, "xlsx"))
        file_menu.addAction(export_xlsx)

        file_menu.addSeparator()
        settings_action = QAction("&Settings…", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        logout_action = QAction("&Log out", self)
        logout_action.triggered.connect(self._logout)
        file_menu.addAction(logout_action)

        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self._quit)
        file_menu.addAction(quit_action)

    def _build_central(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        # Signed-in user banner (Settings / Log out live in the File menu)
        name = auth.current_display_name()
        self.user_label = QLabel(f"Signed in as {name}" if name else "")
        self.user_label.setVisible(bool(name))
        layout.addWidget(self.user_label)

        # Add bar
        add_bar = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste an Amazon product URL…")
        self.url_input.returnPressed.connect(self._add_product)
        self.add_button = QPushButton("Add Product")
        self.add_button.clicked.connect(self._add_product)
        self.refresh_button = QPushButton("Refresh All")
        self.refresh_button.clicked.connect(self._refresh_all)
        add_bar.addWidget(self.url_input, 1)
        add_bar.addWidget(self.add_button)
        add_bar.addWidget(self.refresh_button)
        layout.addLayout(add_bar)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["", "", "Product", "Price", "Stock", "Last checked", "Actions"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # All columns user-resizable; saved widths are restored in _restore_layout.
        for col in range(7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col, width in (
            (COL_MOVE, 84), (COL_IMAGE, 74), (COL_NAME, 320), (COL_PRICE, 110),
            (COL_STOCK, 150), (COL_CHECKED, 140), (COL_ACTIONS, 280),
        ):
            self.table.setColumnWidth(col, width)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.cellClicked.connect(self._open_link)
        layout.addWidget(self.table)

        self.setCentralWidget(central)

        # Bottom-right switch: close to tray vs. exit the app.
        self.tray_checkbox = QCheckBox("Close to tray")
        self.tray_checkbox.setToolTip(
            "On: closing the window keeps it running in the tray.\n"
            "Off: closing exits the app."
        )
        self.statusBar().addPermanentWidget(self.tray_checkbox)
        self.statusBar().showMessage("Ready")

    # --- data → table ------------------------------------------------------

    def reload(self) -> None:
        products = self._sort_products(repo.list_products())
        self.table.setRowCount(0)
        for product in products:
            self._append_row(product)
        self.statusBar().showMessage(f"{len(products)} product(s) tracked")

    # --- sorting -----------------------------------------------------------

    _SORTABLE_COLUMNS = (COL_NAME, COL_PRICE, COL_STOCK, COL_CHECKED)

    def _sort_value(self, product, col):
        if col == COL_NAME:
            return (product.name or product.url or "").casefold()
        if col == COL_PRICE:
            return product.last_price
        if col == COL_STOCK:
            return (product.last_stock or "").casefold() or None
        if col == COL_CHECKED:
            return product.last_checked
        return None

    def _sort_products(self, products):
        if self._sort_column is None:
            return products  # manual / position order from the repository
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        keyed = [(self._sort_value(p, self._sort_column), p) for p in products]
        present = [(v, p) for v, p in keyed if v is not None]
        missing = [p for v, p in keyed if v is None]
        present.sort(key=lambda item: item[0], reverse=reverse)
        return [p for _, p in present] + missing  # missing values always last

    def _on_header_clicked(self, col: int) -> None:
        if col not in self._SORTABLE_COLUMNS:
            return
        if self._sort_column != col:
            self._sort_column = col
            self._sort_order = Qt.SortOrder.AscendingOrder
        elif self._sort_order == Qt.SortOrder.AscendingOrder:
            self._sort_order = Qt.SortOrder.DescendingOrder
        else:
            self._sort_column = None  # third click → back to manual order
        self._apply_sort_indicator()
        self.reload()
        self._save_layout()

    def _apply_sort_indicator(self) -> None:
        header = self.table.horizontalHeader()
        if self._sort_column is None:
            header.setSortIndicatorShown(False)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(self._sort_column, self._sort_order)

    def _append_row(self, product) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setCellWidget(row, COL_MOVE, self._move_buttons(product.id))

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setFixedSize(IMG_SIZE + 6, IMG_SIZE + 6)
        self.table.setCellWidget(row, COL_IMAGE, image_label)
        self._images.load(getattr(product, "image_url", None), image_label, IMG_SIZE)

        name_item = QTableWidgetItem(product.name or product.url)
        name_item.setToolTip(f"Open: {product.url}")
        name_item.setData(Qt.ItemDataRole.UserRole, product.url)
        name_item.setForeground(QColor("#1a4fd6"))  # link blue
        link_font = name_item.font()
        link_font.setUnderline(True)
        name_item.setFont(link_font)
        self.table.setItem(row, COL_NAME, name_item)

        price_item = QTableWidgetItem(format_price(product.last_price, product.currency))
        price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if product.price_changed and product.prev_price is not None:
            price_item.setForeground(_CHANGED_COLOR)
            price_item.setToolTip(f"Was: {format_price(product.prev_price, product.currency)}")
        self.table.setItem(row, COL_PRICE, price_item)

        stock_item = QTableWidgetItem(product.last_stock or "Unknown")
        stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if product.stock_changed and product.prev_stock:
            stock_item.setForeground(_CHANGED_COLOR)
            stock_item.setToolTip(f"Was: {product.prev_stock}")
        self.table.setItem(row, COL_STOCK, stock_item)

        checked = (
            product.last_checked.strftime("%d %b %Y %H:%M") if product.last_checked else "—"
        )
        checked_item = QTableWidgetItem(checked)
        checked_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, COL_CHECKED, checked_item)

        self.table.setCellWidget(row, COL_ACTIONS, self._action_buttons(product.id))

    def _action_buttons(self, product_id: int) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        for label, handler in (
            ("Graph", self._show_graph),
            ("Edit", self._edit_product),
            ("Delete", self._delete_product),
        ):
            button = QPushButton(label)
            button.clicked.connect(partial(handler, product_id))
            layout.addWidget(button)
        return widget

    def _move_buttons(self, product_id: int) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        up = QToolButton()
        up.setArrowType(Qt.ArrowType.UpArrow)
        down = QToolButton()
        down.setArrowType(Qt.ArrowType.DownArrow)
        for button, tip, delta in ((up, "Move up", -1), (down, "Move down", 1)):
            button.setToolTip(tip)
            button.setFixedSize(32, 30)
            button.clicked.connect(partial(self._move, product_id, delta))
            layout.addWidget(button)
        return widget

    def _move(self, product_id: int, delta: int) -> None:
        # Reorder against the order currently shown (which may be sorted).
        displayed = self._sort_products(repo.list_products())
        ids = [p.id for p in displayed]
        if product_id not in ids:
            return
        i = ids.index(product_id)
        j = i + delta
        if j < 0 or j >= len(ids):
            return  # already at the edge
        ids[i], ids[j] = ids[j], ids[i]
        repo.reorder_products(ids)
        # A manual move commits to manual ordering so the change is visible.
        if self._sort_column is not None:
            self._sort_column = None
            self._apply_sort_indicator()
        self.reload()
        self._save_layout()

    # --- add / refresh (async scraping) ------------------------------------

    def _add_product(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.information(self, "Add product", "Please paste a product URL.")
            return
        self.add_button.setEnabled(False)
        self.statusBar().showMessage("Fetching product…")
        self._start_task(url, key="__add__", on_finished=self._on_added)

    def _on_added(self, _key, data) -> None:
        self.add_button.setEnabled(True)
        if not data.ok:
            QMessageBox.warning(self, "Could not add product", data.error or "Unknown error.")
            self.statusBar().showMessage("Add failed")
            return
        repo.add_product(data.url, data.name, data.price, data.currency, data.stock,
                         image_url=data.image_url)
        self.url_input.clear()
        self.reload()
        self.statusBar().showMessage(f"Added: {data.name}")

    def _refresh_all(self) -> None:
        """Manual refresh: re-scrape all + log a history point per product."""
        self._run_refresh(snapshot=True, notify=False)

    def _auto_refresh(self) -> None:
        """5-minute timer: re-scrape all, update display, notify on changes."""
        self._run_refresh(snapshot=False, notify=True)

    def _run_refresh(self, *, snapshot: bool, notify: bool) -> None:
        if self._pending_refresh > 0:
            return  # a batch is already running
        products = repo.list_products()
        if not products:
            return
        self._refresh_snapshot = snapshot
        self._refresh_notify = notify
        self._refresh_changes = []
        self._pending_refresh = len(products)
        self.refresh_button.setEnabled(False)
        self.statusBar().showMessage(f"Refreshing {self._pending_refresh} product(s)…")
        for product in products:
            self._start_task(product.url, key=product.id, on_finished=self._on_refreshed)

    def _on_refreshed(self, product_id, data) -> None:
        if data.ok:
            product = repo.apply_scrape_result(
                product_id,
                name=data.name,
                price=data.price,
                currency=data.currency,
                stock=data.stock,
                image_url=data.image_url,
            )
            if product is not None:
                if self._refresh_snapshot:
                    repo.record_price_snapshot(
                        product_id, price=product.last_price, stock=product.last_stock
                    )
                if product.price_changed or product.stock_changed:
                    self._refresh_changes.append(product.name or product.url)
        self._pending_refresh -= 1
        if self._pending_refresh <= 0:
            self._finalize_refresh()

    def _finalize_refresh(self) -> None:
        self.refresh_button.setEnabled(True)
        self.reload()
        changed = self._refresh_changes
        if changed and self._refresh_notify and self._tray_available:
            summary = ", ".join(changed[:5]) + ("…" if len(changed) > 5 else "")
            self.tray_icon.showMessage(
                "Price / stock changed",
                summary,
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
        if changed:
            self.statusBar().showMessage(f"Refresh complete — {len(changed)} change(s) detected")
        else:
            self.statusBar().showMessage("Refresh complete")

    def _take_snapshot(self) -> None:
        """Hourly timer: log current price/stock to history without re-scraping."""
        products = repo.list_products()
        for product in products:
            repo.record_price_snapshot(
                product.id, price=product.last_price, stock=product.last_stock
            )
        if products:
            self.statusBar().showMessage(f"Logged hourly snapshot for {len(products)} product(s)")

    def _start_task(self, url: str, key, on_finished) -> None:
        task = ScrapeTask(url, key=key)
        task.signals.finished.connect(on_finished)
        task.signals.finished.connect(partial(self._discard_task, task))
        self._tasks.append(task)
        self._pool.start(task)

    def _discard_task(self, task, *_args) -> None:
        if task in self._tasks:
            self._tasks.remove(task)

    # --- scheduling & system tray ------------------------------------------

    def _start_timers(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(REFRESH_INTERVAL_MS)

        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.timeout.connect(self._take_snapshot)
        self._snapshot_timer.start(SNAPSHOT_INTERVAL_MS)

    def _build_tray(self) -> None:
        icon = app_icon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self._tray_available:
            return
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Price Tracker")
        menu = QMenu()
        menu.addAction("Show", self._restore_window)
        menu.addAction("Refresh now", self._refresh_all)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _restore_layout(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        # _v2: layout defaults changed (taller rows, wider columns), so old saved
        # column widths are intentionally ignored.
        header_state = self._settings.value("header_state_v4")
        if header_state is not None:
            self.table.horizontalHeader().restoreState(header_state)
        close_to_tray = self._settings.value("close_to_tray", True, type=bool)
        self.tray_checkbox.setChecked(bool(close_to_tray) and self._tray_available)
        self.tray_checkbox.setEnabled(self._tray_available)

        try:
            sort_col = int(self._settings.value("sort_column", -1))
        except (TypeError, ValueError):
            sort_col = -1
        self._sort_column = None if sort_col < 0 else sort_col
        try:
            sort_ord = int(self._settings.value("sort_order", 0))
        except (TypeError, ValueError):
            sort_ord = 0
        self._sort_order = (
            Qt.SortOrder.DescendingOrder if sort_ord == 1 else Qt.SortOrder.AscendingOrder
        )
        self._apply_sort_indicator()

    def _save_layout(self) -> None:
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("header_state_v4", self.table.horizontalHeader().saveState())
        self._settings.setValue("close_to_tray", self.tray_checkbox.isChecked())
        self._settings.setValue("sort_column", -1 if self._sort_column is None else self._sort_column)
        self._settings.setValue("sort_order", self._sort_order.value)

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    def _quit(self) -> None:
        self._really_quit = True
        self._save_layout()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        QApplication.instance().quit()

    def _open_settings(self) -> None:
        SettingsDialog(self).exec()
        # Name may have changed — refresh the banner.
        name = auth.current_display_name()
        self.user_label.setText(f"Signed in as {name}" if name else "")
        self.user_label.setVisible(bool(name))

    def _logout(self) -> None:
        confirm = QMessageBox.question(
            self, "Log out", "Log out? You'll need to sign in again next time."
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        # Close the window for real so main.py can return to the login screen.
        self.logout_requested = True
        self._really_quit = True
        self._save_layout()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.close()

    def closeEvent(self, event) -> None:
        self._save_layout()
        # The bottom-right "Close to tray" switch decides: keep running vs. exit.
        close_to_tray = self.tray_checkbox.isChecked() and self._tray_available
        if self._really_quit or not close_to_tray:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Price Tracker",
            "Still tracking in the background. Use the tray icon to reopen or quit.",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    # --- row actions -------------------------------------------------------

    def _open_link(self, row: int, col: int) -> None:
        if col != COL_NAME:
            return
        item = self.table.item(row, COL_NAME)
        url = item.data(Qt.ItemDataRole.UserRole) if item else None
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _show_graph(self, product_id: int) -> None:
        product = repo.get_product(product_id)
        if product is not None:
            GraphDialog(product, parent=self).exec()

    def _edit_product(self, product_id: int) -> None:
        product = repo.get_product(product_id)
        if product is None:
            return
        dialog = EditProductDialog(product.name or "", product.url, parent=self)
        if dialog.exec() == EditProductDialog.DialogCode.Accepted:
            name, url = dialog.values()
            repo.update_product(product_id, name=name, url=url)
            self.reload()

    def _delete_product(self, product_id: int) -> None:
        product = repo.get_product(product_id)
        if product is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete product",
            f"Delete '{product.name or product.url}' and its price history?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            repo.delete_product(product_id)
            self.reload()

    # --- export ------------------------------------------------------------

    def _export(self, fmt: str) -> None:
        if not repo.list_products():
            QMessageBox.information(self, "Export", "There are no products to export.")
            return

        timescale, ok = QInputDialog.getItem(
            self, "Export timescale", "Include history from:",
            TIMESCALE_LABELS, TIMESCALE_LABELS.index(DEFAULT_TIMESCALE), False,
        )
        if not ok:
            return

        if fmt == "xlsx":
            filt, default = "Excel files (*.xlsx)", "price_history.xlsx"
        else:
            filt, default = "CSV files (*.csv)", "price_history.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save export", default, filt)
        if not path:
            return

        try:
            rows = export_service.export_to_file(path, timescale)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Exported {rows} row(s) to {path}")
