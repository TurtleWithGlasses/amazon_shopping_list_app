"""Main application window: product table, add/refresh, edit/delete, graph, export."""
import os
from datetime import datetime, timedelta, timezone
from functools import partial
from urllib.parse import quote_plus, urlparse

from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
from core.cloud import auth, session_store
from core.scraping.registry import get_adapter
from core.version import GITHUB_REPO, __version__
from services import export as export_service
from services.notifications import NotificationService
from services.scrape_worker import ScrapeTask
from services.suggestions import complement_terms
from services.trend import price_trend
from services.stock import OUT_OF_STOCK, classify_stock
from services.telegram import TelegramNotifier
from services.updater import DownloadTask, UpdateCheckTask
from services.timescales import DEFAULT_TIMESCALE, TIMESCALE_LABELS
from ui.changes_dialog import StartupChangesDialog
from ui.edit_dialog import EditProductDialog
from ui.graph_dialog import GraphDialog
from ui.icons import app_icon
from ui.image_cache import ImageLoader
from ui.logos import logo_key, logo_pixmap
from ui.notifications import TrayChannel
from ui.settings_dialog import SettingsDialog
from ui.formatting import format_price
from ui.theme import link_color

_INCREASE_COLOR = QColor("#c9a000")  # yellow/gold: stock level went up
_DECREASE_COLOR = QColor("#2e9e44")  # green: price or stock went down
_CHANGED_COLOR = QColor("#e8830c")   # orange: changed, direction indeterminate
_PRICE_UP_COLOR = QColor("#cc3b3b")  # red: price rose (buyer's view; matches notifications)

(COL_NUM, COL_MOVE, COL_LOGO, COL_IMAGE, COL_NAME, COL_PRICE, COL_TREND,
 COL_STOCK, COL_CHECKED, COL_STATUS, COL_ACTIONS) = range(11)
COLUMN_COUNT = 11

# Price-trend indicator (Phase 37): glyph, color, label by state name.
_TREND_STYLES = {
    "falling": ("▼", _DECREASE_COLOR, "Falling"),
    "rising": ("▲", _PRICE_UP_COLOR, "Rising"),
    "stable": ("→", QColor("#888888"), "Stable"),
    "unknown": ("", None, ""),
}
_ROW_NUM_COLOR = QColor("#888888")  # muted index numbers, readable on light/dark

# Per-row fetch status (glyph, color, tooltip default) keyed by state name.
_STATUS_STYLES = {
    "idle": ("", "#888888", ""),
    "refreshing": ("⟳", "#c9a000", "Refreshing…"),
    "ok": ("✓", "#2e9e44", "Updated"),
    "error": ("✗", "#cc3b3b", "Refresh failed"),
}
IMG_SIZE = 56    # product thumbnail size (px)
LOGO_W, LOGO_H = 72, 36  # retailer logo cell box (px); aspect kept within it
ROW_HEIGHT = 70  # row height; leaves margin around the thumbnail

# Auto-refresh interval options (label, milliseconds). First is the default.
REFRESH_INTERVAL_OPTIONS = [
    ("5 minutes", 5 * 60 * 1000),
    ("15 minutes", 15 * 60 * 1000),
    ("30 minutes", 30 * 60 * 1000),
    ("1 hour", 60 * 60 * 1000),
    ("Never", 0),  # 0 = no auto-refresh; track only on manual command
]
SNAPSHOT_INTERVAL_MS = int(os.environ.get("PRICETRACKER_SNAPSHOT_MS", 60 * 60 * 1000))   # 1 hour


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Price Tracker  v{__version__}")
        self.resize(1000, 600)
        self._pool = QThreadPool.globalInstance()
        # Scraping runs on its own capped pool: a big "Refresh All" must not
        # launch a swarm of Chrome fallbacks (resource exhaustion / crashes),
        # and it must not starve image/notification tasks on the global pool.
        self._scrape_pool = QThreadPool(self)
        self._scrape_pool.setMaxThreadCount(3)
        self._tasks = []          # keep refs so QRunnables aren't GC'd
        self._pending_refresh = 0
        self._refresh_total = 0
        # Per-row widgets, keyed by product id (rebuilt on every reload()).
        self._status_cells = {}        # product id -> status QLabel
        self._row_refresh_buttons = {}  # product id -> per-row Refresh button
        self._row_for_product = {}     # product id -> table row index
        self._single_active = set()    # ids with a single-row refresh in flight
        self._trend_cache = {}         # product id -> (state, pct) over the window
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
        self._notifications = NotificationService()
        self._notifications.add_channel(TelegramNotifier())  # self-gates until configured
        # refresh batch state
        self._refresh_title = "Price / stock changed"
        self._refresh_report = False  # open the changes report window on finalize
        self._refresh_events = []  # detailed change records (notification + report)
        self._target_hits = []     # products whose price hit the target this batch
        self._cart_dialog = None   # open cart, so a refresh can update it live

        self._build_menu()
        self._build_central()
        self._build_tray()
        self._restore_layout()
        self._recompute_trends()  # fill the trend cache before the first render
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
        updates_action = QAction("Check for &updates…", self)
        updates_action.triggered.connect(lambda: self._check_updates(show_no_update=True))
        file_menu.addAction(updates_action)
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        file_menu.addAction(about_action)
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

        # Lists the groups directly (rebuilt each time it opens), with
        # "Manage groups…" below them — one click to open any group.
        self._groups_menu = self.menuBar().addMenu("&Groups")
        self._groups_menu.aboutToShow.connect(self._populate_groups_menu)

        # Shopping cart (Phase 38): open the cart or clear it; label shows count.
        self._cart_menu = self.menuBar().addMenu("&Cart")
        self._cart_menu.aboutToShow.connect(self._populate_cart_menu)

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
        self.add_button.setObjectName("primary")  # M3 filled primary button
        self.add_button.clicked.connect(self._add_product)
        self.refresh_button = QPushButton("Refresh All")
        self.refresh_button.setObjectName("primary")
        self.refresh_button.clicked.connect(self._refresh_all)
        self.interval_combo = QComboBox()
        for label, ms in REFRESH_INTERVAL_OPTIONS:
            self.interval_combo.addItem(label, ms)
        self.interval_combo.setToolTip("How often to automatically re-check all products.")
        self.interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        add_bar.addWidget(self.url_input, 1)
        add_bar.addWidget(self.add_button)
        add_bar.addWidget(self.refresh_button)
        add_bar.addWidget(QLabel("Auto-refresh:"))
        add_bar.addWidget(self.interval_combo)
        layout.addLayout(add_bar)

        # Table
        self.table = QTableWidget(0, COLUMN_COUNT)
        self.table.setHorizontalHeaderLabels(
            ["#", "", "", "", "Product", "Price", "Trend", "Stock",
             "Last checked", "Status", "Actions"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # All columns user-resizable; saved widths are restored in _restore_layout.
        for col in range(COLUMN_COUNT):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col, width in (
            (COL_NUM, 38), (COL_MOVE, 84), (COL_LOGO, 84), (COL_IMAGE, 74),
            (COL_NAME, 320), (COL_PRICE, 110), (COL_TREND, 64), (COL_STOCK, 150),
            (COL_CHECKED, 140), (COL_STATUS, 64), (COL_ACTIONS, 340),
        ):
            self.table.setColumnWidth(col, width)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.cellClicked.connect(self._open_link)
        # Right-click a row → add to / remove from groups (Phase 34).
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_row_menu)
        # Widget cells (arrows/logo/image/status/actions) don't paint the row
        # selection brush like plain item cells do; tint them to match.
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
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

    def _recompute_trends(self, days: int = 7) -> None:
        """Refresh the price-trend cache in one batched history query, so the
        Trend column never costs a per-row query on reload (Phase 37)."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            history = repo.recent_history(since)
        except Exception:
            return  # leave the previous cache; trends just won't update this time
        self._trend_cache = {pid: price_trend(points) for pid, points in history.items()}

    def reload(self) -> None:
        # Preserve the scroll position: rebuilding the table resets the
        # scrollbar to the top, which yanks the view up after Add/refresh/move.
        scroll = self.table.verticalScrollBar().value()
        products = self._sort_products(repo.list_products())
        self.table.setRowCount(0)
        self._status_cells = {}
        self._row_refresh_buttons = {}
        self._row_for_product = {}
        for product in products:
            self._append_row(product)
        # Restore now (clamped to the new range) and again after the view
        # finishes its layout, so the offset sticks even if the range updated late.
        self.table.verticalScrollBar().setValue(scroll)
        QTimer.singleShot(0, lambda: self.table.verticalScrollBar().setValue(scroll))
        self.statusBar().showMessage(f"{len(products)} product(s) tracked")

    # --- sorting -----------------------------------------------------------

    _SORTABLE_COLUMNS = (COL_NAME, COL_PRICE, COL_TREND, COL_STOCK, COL_CHECKED)

    def _sort_value(self, product, col):
        if col == COL_NAME:
            return (product.name or product.url or "").casefold()
        if col == COL_PRICE:
            return product.last_price
        if col == COL_TREND:
            return self._trend_cache.get(product.id, ("unknown", None))[1]  # % change
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

    @staticmethod
    def _format_local(dt) -> str:
        """Format a stored (UTC) timestamp in the user's local timezone."""
        if dt is None:
            return "—"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # local backend stores naive UTC
        return dt.astimezone().strftime("%d %b %Y %H:%M")  # astimezone() → system local

    def _fill_value_cells(self, row: int, product) -> None:
        """Set the price / stock / last-checked cells for a row from a product.
        Shared by row creation and the in-place single-row refresh update."""
        text = format_price(product.last_price, product.currency)
        tips = []
        if product.price_changed and product.prev_price is not None and product.last_price is not None:
            # Inline arrow next to the price (red ▲ up / green ▼ down). On a later
            # scan with no change, price_changed is False so the arrow disappears.
            text += "  " + ("▲" if product.last_price > product.prev_price else "▼")
            tips.append(f"Was: {format_price(product.prev_price, product.currency)}")
        target = getattr(product, "target_price", None)
        if target is not None:
            tips.append(f"Target: {format_price(target, product.currency)}")
            if self._target_met(product):
                text += "  🎯"  # current price is at/below the user's target
        price_item = QTableWidgetItem(text)
        price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if product.price_changed and product.prev_price is not None:
            price_item.setForeground(self._price_change_color(product.prev_price, product.last_price))
        if tips:
            price_item.setToolTip(" · ".join(tips))
        self.table.setItem(row, COL_PRICE, price_item)

        # Price trend over the window (Phase 37), from the batched cache.
        state, pct = self._trend_cache.get(product.id, ("unknown", None))
        glyph, color, label = _TREND_STYLES[state]
        trend_item = QTableWidgetItem(glyph)
        trend_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if color is not None:
            trend_item.setForeground(color)
        if pct is not None:
            trend_item.setData(Qt.ItemDataRole.UserRole, pct)  # for sorting
            trend_item.setToolTip(f"{label} {pct:+.1f}% over 7 days")
        self.table.setItem(row, COL_TREND, trend_item)

        stock_item = QTableWidgetItem(product.last_stock or "Unknown")
        stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if product.stock_changed and product.prev_stock:
            stock_item.setForeground(self._stock_change_color(product.prev_stock, product.last_stock))
            stock_item.setToolTip(f"Was: {product.prev_stock}")
        self.table.setItem(row, COL_STOCK, stock_item)

        checked = self._format_local(product.last_checked)
        checked_item = QTableWidgetItem(checked)
        checked_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, COL_CHECKED, checked_item)

    def _update_row(self, product_id) -> None:
        """Refresh just one row's value cells in place (no full reload), so the
        scroll position and focus aren't disturbed by a single-row refresh."""
        row = self._row_for_product.get(product_id)
        product = repo.get_product(product_id)
        if row is None or product is None:
            self.reload()  # fallback: product not currently shown
            return
        self._fill_value_cells(row, product)

    def _append_row(self, product) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._row_for_product[product.id] = row  # for in-place single-row updates

        num_item = QTableWidgetItem(str(row + 1))  # 1-based display position
        num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        num_item.setForeground(_ROW_NUM_COLOR)
        num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row, COL_NUM, num_item)

        self.table.setCellWidget(row, COL_MOVE, self._move_buttons(product.id))

        logo_label = QLabel()
        logo_label.setObjectName("rowcell")  # transparent over the row color
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = logo_pixmap(product, LOGO_W, LOGO_H)
        if pixmap is not None:
            logo_label.setPixmap(pixmap)
        logo_label.setToolTip(logo_key(product))
        self.table.setCellWidget(row, COL_LOGO, logo_label)

        image_label = QLabel()
        image_label.setObjectName("rowcell")
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setFixedSize(IMG_SIZE + 6, IMG_SIZE + 6)
        self.table.setCellWidget(row, COL_IMAGE, image_label)
        self._images.load(getattr(product, "image_url", None), image_label, IMG_SIZE)

        name_item = QTableWidgetItem(product.name or product.url)
        name_item.setToolTip(f"Open: {product.url}")
        name_item.setData(Qt.ItemDataRole.UserRole, product.url)
        name_item.setForeground(link_color())  # theme-harmonized link color
        link_font = name_item.font()
        link_font.setUnderline(True)
        name_item.setFont(link_font)
        self.table.setItem(row, COL_NAME, name_item)

        self._fill_value_cells(row, product)

        status_label = QLabel()
        status_label.setObjectName("rowcell")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, COL_STATUS, status_label)
        self._status_cells[product.id] = status_label

        self.table.setCellWidget(row, COL_ACTIONS, self._action_buttons(product.id))

    @staticmethod
    def _price_change_color(prev, new) -> QColor:
        if prev is None or new is None or new == prev:
            return _CHANGED_COLOR
        return _PRICE_UP_COLOR if new > prev else _DECREASE_COLOR  # red up, green down

    @staticmethod
    def _stock_change_color(prev, new) -> QColor:
        prev_level, prev_qty = classify_stock(prev or "")
        new_level, new_qty = classify_stock(new or "")
        if prev_level is not None and new_level is not None and prev_level != new_level:
            return _INCREASE_COLOR if new_level > prev_level else _DECREASE_COLOR
        if prev_qty is not None and new_qty is not None and prev_qty != new_qty:
            return _INCREASE_COLOR if new_qty > prev_qty else _DECREASE_COLOR
        return _CHANGED_COLOR  # changed but direction indeterminate

    @staticmethod
    def _target_met(product) -> bool:
        """True when the current price is at or below the user's target price."""
        target = getattr(product, "target_price", None)
        return (target is not None and product.last_price is not None
                and product.last_price <= target)

    @classmethod
    def _target_newly_hit(cls, product) -> bool:
        """True only when this scan moved the price from above the target to
        at/below it — so we alert on the crossing, not on every scan after."""
        if not cls._target_met(product):
            return False
        target = product.target_price
        return bool(product.price_changed and product.prev_price is not None
                    and product.prev_price > target)

    def _set_row_status(self, product_id, state: str, tooltip: str = None) -> None:
        """Update a row's fetch indicator (idle/refreshing/ok/error)."""
        label = self._status_cells.get(product_id)
        if label is None:
            return
        glyph, color, default_tip = _STATUS_STYLES[state]
        label.setText(glyph)
        label.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")
        label.setToolTip(default_tip if tooltip is None else tooltip)

    # Cells backed by widgets (not QTableWidgetItems) — these don't get the
    # selection brush for free, so we tint them on selection change.
    _WIDGET_COLUMNS = (COL_MOVE, COL_LOGO, COL_IMAGE, COL_STATUS, COL_ACTIONS)

    def _on_selection_changed(self) -> None:
        selected = {ix.row() for ix in self.table.selectionModel().selectedRows()}
        highlight = self.table.palette().color(QPalette.ColorRole.Highlight)
        for row in range(self.table.rowCount()):
            self._tint_row_widgets(row, row in selected, highlight)

    def _tint_row_widgets(self, row: int, on: bool, highlight: QColor) -> None:
        # A stylesheet scoped to the container (#rowcell) paints the cell's
        # background to match the selection while leaving child buttons/labels
        # styled normally. The palette/Window role is unreliable here because
        # these containers don't all use Window as their background role.
        css = f"#rowcell {{ background-color: {highlight.name()}; }}" if on else ""
        for col in self._WIDGET_COLUMNS:
            widget = self.table.cellWidget(row, col)
            if widget is None:
                continue
            widget.setObjectName("rowcell")
            widget.setStyleSheet(css)

    def _action_buttons(self, product_id: int) -> QWidget:
        widget = QWidget()
        widget.setObjectName("rowcell")  # transparent over the row color
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Re-scrape just this product")
        refresh_btn.clicked.connect(partial(self._refresh_one, product_id))
        refresh_btn.setEnabled(self._pending_refresh == 0)  # disabled mid-batch
        layout.addWidget(refresh_btn)
        self._row_refresh_buttons[product_id] = refresh_btn
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
        widget.setObjectName("rowcell")  # transparent over the row color
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

    @staticmethod
    def _canonical_url(url: str) -> str:
        """Compare-friendly form: no scheme, no www, no query, no trailing slash."""
        parsed = urlparse(url or "")
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{parsed.path.rstrip('/')}"

    def _add_product(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.information(self, "Add product", "Please paste a product URL.")
            return
        # Reject duplicates up front (compare the canonical, query-stripped URL;
        # normalize first so Amazon /dp vs /gp forms of the same item also match).
        adapter = get_adapter(url)
        normalized = adapter.normalize_url(url) if adapter else url
        target = self._canonical_url(normalized)
        if any(self._canonical_url(p.url) == target for p in repo.list_products()):
            QMessageBox.warning(
                self, "Already on your list",
                "The product you are trying to add already exists on your list.",
            )
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
        """Manual refresh: re-scrape all, log a history point, and notify
        (tray + Telegram) on any price/stock change — same as the auto-refresh."""
        self._run_refresh(snapshot=True, notify=True)

    def _refresh_one(self, product_id) -> None:
        """Re-scrape a single product without touching the rest of the table."""
        if self._pending_refresh > 0 or product_id in self._single_active:
            return  # a batch is running, or this row is already refreshing
        product = repo.get_product(product_id)
        if product is None:
            return
        # NOTE: don't disable this row's button — it currently has keyboard focus
        # (the user just clicked it), and disabling a focused widget makes Qt move
        # focus elsewhere, scrolling the table away. Re-clicks are already blocked
        # by the _single_active gate above, and the "⟳" status shows it's busy.
        self._single_active.add(product_id)
        self._set_row_status(product_id, "refreshing")
        self.statusBar().showMessage(f"Refreshing {product.name or product.url}…")
        self._start_task(product.url, key=product_id, on_finished=self._on_one_refreshed)

    def _on_one_refreshed(self, product_id, data) -> None:
        self._single_active.discard(product_id)
        ok, message, hit = data.ok, None, None
        if data.ok:
            try:
                product, _changed, _back, target_hit = self._persist_scrape(
                    product_id, data, snapshot=True
                )
                if target_hit:
                    hit = self._target_hit_record(product)
            except Exception as exc:
                ok, message = False, str(exc)
        else:
            message = data.error or "Scrape failed"
        # Update only this row in place (no full reload) so the scroll position
        # and focus stay put, then set the indicator.
        self._recompute_trends()  # this product gained a history point
        self._update_row(product_id)
        self._refresh_cart_if_open()  # reflect the new price in an open cart
        if ok:
            self._set_row_status(product_id, "ok")
            self.statusBar().showMessage("Refresh complete")
            if hit is not None:
                self._notify_target_hits([hit])
        else:
            self._set_row_status(product_id, "error", message)
            self.statusBar().showMessage(f"Refresh failed: {message}")

    def _auto_refresh(self) -> None:
        """5-minute timer: re-scrape all, update display, notify on changes."""
        self._run_refresh(snapshot=False, notify=True, title="Price / stock changed")

    def _startup_check(self) -> None:
        """One-shot at launch: detect what changed since the last session and
        report it in a window."""
        self._run_refresh(snapshot=False, notify=True,
                          title="While you were away", report=True)

    def _run_refresh(self, *, snapshot: bool, notify: bool,
                     title: str = "Price / stock changed", report: bool = False) -> None:
        if self._pending_refresh > 0:
            return  # a batch is already running
        products = repo.list_products()
        if not products:
            return
        self._refresh_snapshot = snapshot
        self._refresh_notify = notify
        self._refresh_title = title
        self._refresh_report = report
        self._refresh_events = []
        self._target_hits = []
        self._pending_refresh = len(products)
        self._refresh_total = len(products)
        self.refresh_button.setEnabled(False)
        for button in self._row_refresh_buttons.values():
            button.setEnabled(False)  # no single-row refresh mid-batch
        for product in products:
            self._set_row_status(product.id, "refreshing")
        self.statusBar().showMessage(f"Refreshing 0/{self._refresh_total}…")
        for product in products:
            self._start_task(product.url, key=product.id, on_finished=self._on_refreshed)

    @staticmethod
    def _is_back_in_stock(prev_stock, new_stock) -> bool:
        """True if availability went from out-of-stock to available."""
        if not prev_stock or not new_stock:
            return False
        prev_level, _ = classify_stock(prev_stock)
        new_level, _ = classify_stock(new_stock)
        return prev_level == OUT_OF_STOCK and new_level is not None and new_level > OUT_OF_STOCK

    def _on_refreshed(self, product_id, data) -> None:
        if data.ok:
            try:
                self._apply_refresh_result(product_id, data)
                self._set_row_status(product_id, "ok")
            except Exception as exc:
                # A network/DB blip on one product must not break the batch.
                self._set_row_status(product_id, "error", str(exc))
                self.statusBar().showMessage(f"Could not save update: {exc}")
        else:
            self._set_row_status(product_id, "error", data.error or "Scrape failed")
        self._pending_refresh -= 1
        done = self._refresh_total - self._pending_refresh
        self.statusBar().showMessage(f"Refreshing {done}/{self._refresh_total}…")
        if self._pending_refresh <= 0:
            self._finalize_refresh()

    def _persist_scrape(self, product_id, data, *, snapshot: bool):
        """Apply one scrape result to the store and log history when warranted.

        Shared by the batch refresh and the per-row refresh. Returns
        ``(product, changed, back_in_stock, target_hit)`` or ``(None, False,
        False, False)``.
        """
        product = repo.apply_scrape_result(
            product_id,
            name=data.name,
            price=data.price,
            currency=data.currency,
            stock=data.stock,
            image_url=data.image_url,
        )
        if product is None:
            return None, False, False, False
        changed = product.price_changed or product.stock_changed
        # Log history on a manual snapshot, OR whenever a change is detected — so
        # the graph captures every price/stock change, not just hourly ones.
        if snapshot or changed:
            repo.record_price_snapshot(
                product_id, price=product.last_price, stock=product.last_stock
            )
        back = bool(product.stock_changed
                    and self._is_back_in_stock(product.prev_stock, product.last_stock))
        return product, changed, back, self._target_newly_hit(product)

    def _target_hit_record(self, product) -> dict:
        return {
            "name": product.name or product.url,
            "site": self._site_name(product.url),
            "currency": product.currency,
            "price": product.last_price,
            "target": product.target_price,
        }

    def _apply_refresh_result(self, product_id, data) -> None:
        product, changed, back, target_hit = self._persist_scrape(
            product_id, data, snapshot=self._refresh_snapshot
        )
        if product is None:
            return
        if target_hit:
            self._target_hits.append(self._target_hit_record(product))
        label = product.name or product.url
        if changed:
            self._refresh_events.append({
                "name": label,
                "site": self._site_name(product.url),
                "currency": product.currency,
                "price_changed": product.price_changed,
                "prev_price": product.prev_price,
                "last_price": product.last_price,
                "stock_changed": product.stock_changed,
                "prev_stock": product.prev_stock,
                "last_stock": product.last_stock,
                "back_in_stock": back,
            })

    @staticmethod
    def _site_name(url: str) -> str:
        """Short store name from a URL, e.g. www.hepsiburada.com -> 'Hepsiburada',
        tr.aliexpress.com -> 'Aliexpress' (drop www and TLD parts like com/gen/tr)."""
        host = urlparse(url or "").netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        tlds = {"com", "net", "org", "co", "gen", "tr", "gov", "edu"}
        while len(parts) > 1 and parts[-1] in tlds:
            parts.pop()
        site = parts[-1] if parts else host
        return site.capitalize()

    def _changes_message(self, limit: int = 25) -> str:
        """Readable per-product change list for the notification body.

        Price moves get a direction arrow at the end of the line (user
        convention: red/up = price rose, green/down = price fell).
        """
        up, down = "🔴⬆️", "🟢⬇️"
        lines = []
        for ev in self._refresh_events[:limit]:
            name = ev["name"] or ""
            if len(name) > 55:
                name = name[:54] + "…"
            site = ev.get("site") or ""
            header = f"• {site} · {name}" if site else f"• {name}"
            lines.append(header)
            cur = ev["currency"] or ""
            if ev["price_changed"] and ev["last_price"] is not None:
                new = format_price(ev["last_price"], cur)
                if ev["prev_price"] is not None:
                    prev = format_price(ev["prev_price"], cur)
                    arrow = up if ev["last_price"] > ev["prev_price"] else down
                    lines.append(f"    {prev} → {new}  {arrow}")
                else:
                    lines.append(f"    {new}")
            if ev["back_in_stock"]:
                lines.append("    ✅ Back in stock")
            elif ev["stock_changed"]:
                lines.append(f"    📦 {ev['prev_stock'] or '—'} → {ev['last_stock'] or '—'}")
        remaining = len(self._refresh_events) - limit
        if remaining > 0:
            lines.append(f"…and {remaining} more")
        return "\n".join(lines)

    def _notify_target_hits(self, hits) -> None:
        """Send a target-price-reached alert (always — it's an explicit alert)."""
        if not hits:
            return
        lines = []
        for h in hits:
            name = (h["name"] or "")[:55]
            prefix = f"{h['site']} · " if h.get("site") else ""
            price = format_price(h["price"], h["currency"])
            target = format_price(h["target"], h["currency"])
            lines.append(f"• {prefix}{name}\n    {price}  (target {target})")
        self._notifications.notify("🎯 Target price reached", "\n".join(lines))

    def _finalize_refresh(self) -> None:
        self.refresh_button.setEnabled(True)
        self._recompute_trends()  # new history points may change the trends
        self.reload()
        self._refresh_cart_if_open()  # reflect new prices in an open cart

        total = len(self._refresh_events)
        if self._refresh_notify and self._refresh_events:
            self._notifications.notify(self._refresh_title, self._changes_message())
        self._notify_target_hits(self._target_hits)
        self.statusBar().showMessage(
            f"Refresh complete — {total} change(s) detected" if total else "Refresh complete"
        )

        # Startup report window: only for the launch batch, only if changes.
        if self._refresh_report and self._refresh_events:
            rows = [self._event_row(e) for e in self._refresh_events]
            self._changes_dialog = StartupChangesDialog(rows, parent=self)
            self._changes_dialog.show()

    def _event_row(self, event) -> tuple:
        if event["price_changed"] and event["prev_price"] is not None:
            price_text = (f"{format_price(event['prev_price'], event['currency'])}"
                          f" → {format_price(event['last_price'], event['currency'])}")
        else:
            price_text = "—"
        if event["back_in_stock"]:
            stock_text = "Back in stock"
        elif event["stock_changed"]:
            stock_text = f"{event['prev_stock'] or '—'} → {event['last_stock'] or '—'}"
        else:
            stock_text = "—"
        return (event["name"], price_text, stock_text)

    def _take_snapshot(self) -> None:
        """Hourly timer: log current price/stock to history without re-scraping."""
        self._persist_session()  # keep the saved token fresh as it rotates
        products = repo.list_products()
        for product in products:
            repo.record_price_snapshot(
                product.id, price=product.last_price, stock=product.last_stock
            )
        if products:
            self.statusBar().showMessage(f"Logged hourly snapshot for {len(products)} product(s)")

    def _persist_session(self) -> None:
        """Re-save the current (possibly rotated) Supabase refresh token, so a
        long-running session doesn't leave a stale token that forces a re-login
        on the next launch. No-op if "remember me" isn't active."""
        try:
            if session_store.has_saved_session():
                token = auth.current_refresh_token()
                if token:
                    session_store.save_session(token, auth.current_email() or "")
        except Exception:
            pass

    def _start_task(self, url: str, key, on_finished) -> None:
        task = ScrapeTask(url, key=key)
        task.signals.finished.connect(on_finished)
        task.signals.finished.connect(partial(self._discard_task, task))
        self._tasks.append(task)
        self._scrape_pool.start(task)

    def _discard_task(self, task, *_args) -> None:
        if task in self._tasks:
            self._tasks.remove(task)

    # --- scheduling & system tray ------------------------------------------

    def _apply_refresh_interval(self, ms) -> None:
        """Start the auto-refresh timer, or stop it when 'Never' (ms 0) is set."""
        if ms and int(ms) > 0:
            self._refresh_timer.start(int(ms))
        else:
            self._refresh_timer.stop()  # "Never" — manual refresh only

    def _start_timers(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._apply_refresh_interval(self.interval_combo.currentData())

        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.timeout.connect(self._take_snapshot)
        self._snapshot_timer.start(SNAPSHOT_INTERVAL_MS)

        # No auto-refresh on startup (it froze the app launching many scrapes at
        # once). Refreshing happens on the periodic timer or via "Refresh All".
        # Quiet update check on startup (notifies only if a newer release exists).
        QTimer.singleShot(4000, lambda: self._check_updates(show_no_update=False))

    def _on_interval_changed(self) -> None:
        ms = self.interval_combo.currentData()
        self._settings.setValue("refresh_interval_ms", ms)
        if hasattr(self, "_refresh_timer"):
            self._apply_refresh_interval(ms)  # applies immediately
        if ms and int(ms) > 0:
            self.statusBar().showMessage(f"Auto-refresh every {self.interval_combo.currentText()}")
        else:
            self.statusBar().showMessage("Auto-refresh off — use Refresh All to check manually")

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
        self._notifications.add_channel(TrayChannel(self.tray_icon))

    def _restore_layout(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        # restoreGeometry usually re-applies the maximized state, but an explicit
        # flag is more reliable across the show() in main.py — re-maximize once
        # the event loop starts if we were maximized when last saved.
        if self._settings.value("window_maximized", False, type=bool):
            QTimer.singleShot(0, self.showMaximized)
        # _v2: layout defaults changed (taller rows, wider columns), so old saved
        # column widths are intentionally ignored.
        header_state = self._settings.value("header_state_v8")
        if header_state is not None:
            self.table.horizontalHeader().restoreState(header_state)
        close_to_tray = self._settings.value("close_to_tray", True, type=bool)
        self.tray_checkbox.setChecked(bool(close_to_tray) and self._tray_available)
        self.tray_checkbox.setEnabled(self._tray_available)

        saved_interval = self._settings.value("refresh_interval_ms")
        if saved_interval is not None:
            try:
                idx = self.interval_combo.findData(int(saved_interval))
            except (TypeError, ValueError):
                idx = -1
            if idx >= 0:
                self.interval_combo.blockSignals(True)
                self.interval_combo.setCurrentIndex(idx)
                self.interval_combo.blockSignals(False)

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
        self._settings.setValue("window_maximized", self.isMaximized() or self.isFullScreen())
        self._settings.setValue("header_state_v8", self.table.horizontalHeader().saveState())
        self._settings.setValue("close_to_tray", self.tray_checkbox.isChecked())
        self._settings.setValue("sort_column", -1 if self._sort_column is None else self._sort_column)
        self._settings.setValue("sort_order", self._sort_order.value)

    def _restore_window(self) -> None:
        # Reopen in the same state it was hidden in (don't force "normal", which
        # would drop a maximized/full-screen window down to a small window).
        if self.isMaximized():
            self.showMaximized()
        elif self.isFullScreen():
            self.showFullScreen()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    def _quit(self) -> None:
        self._really_quit = True
        self._save_layout()
        self._persist_session()  # persist the latest token so next launch restores
        if self.tray_icon is not None:
            self.tray_icon.hide()
        QApplication.instance().quit()

    def _check_updates(self, show_no_update: bool) -> None:
        task = UpdateCheckTask()
        task.signals.finished.connect(
            lambda info: self._on_update_checked(info, show_no_update)
        )
        task.signals.finished.connect(partial(self._discard_task, task))
        self._tasks.append(task)
        self._pool.start(task)

    def _on_update_checked(self, info, show_no_update: bool) -> None:
        if info is None:
            if show_no_update:
                QMessageBox.information(
                    self, "Updates",
                    f"You're on the latest version ({__version__}).",
                )
            return
        if info.asset_url:
            answer = QMessageBox.question(
                self, "Update available",
                f"Version {info.latest} is available (you have {__version__}).\n"
                f"Download and install it now? The app will close to finish installing.",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._download_update(info)
        else:
            # No installer attached to the release — fall back to opening the page.
            answer = QMessageBox.question(
                self, "Update available",
                f"Version {info.latest} is available (you have {__version__}).\n"
                f"Open the download page?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl(info.url))

    def _download_update(self, info) -> None:
        self.statusBar().showMessage("Downloading update… 0%")
        task = DownloadTask(info.asset_url)
        task.signals.progress.connect(self._on_update_progress)
        task.signals.finished.connect(self._on_update_downloaded)
        task.signals.finished.connect(partial(self._discard_task, task))
        self._tasks.append(task)
        self._pool.start(task)

    def _on_update_progress(self, done: int, total: int) -> None:
        pct = int(done * 100 / total) if total else 0
        self.statusBar().showMessage(f"Downloading update… {pct}%")

    def _on_update_downloaded(self, path) -> None:
        if not path:
            QMessageBox.warning(self, "Update", "The update download failed. Please try again later.")
            self.statusBar().showMessage("Update download failed")
            return
        QMessageBox.information(
            self, "Update ready",
            "The installer will open now and Price Tracker will close so the update "
            "can finish.\n\nIf Windows shows a SmartScreen warning, choose "
            "\"More info\" → \"Run anyway\".",
        )
        try:
            import subprocess
            import sys
            if sys.platform == "win32":
                os.startfile(path)  # noqa: type-checker (Windows-only)
            else:
                subprocess.Popen([path])
        except Exception as exc:
            QMessageBox.warning(self, "Update", f"Could not launch the installer:\n{exc}")
            return
        self._quit()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About Price Tracker",
            f"<b>Price Tracker</b><br>"
            f"Version {__version__}<br><br>"
            f"Tracks price &amp; stock across Amazon and other e-commerce sites, "
            f"with history graphs, change alerts, and Telegram notifications.<br><br>"
            f"<a href='https://github.com/{GITHUB_REPO}'>github.com/{GITHUB_REPO}</a>",
        )

    # --- groups (Phase 34) -------------------------------------------------

    def _populate_groups_menu(self) -> None:
        """Rebuild the Groups menu: a row per group (opens it), then Manage…"""
        self._groups_menu.clear()
        groups = repo.list_groups()
        for group in groups:
            self._groups_menu.addAction(
                f"{group.name}  ({group.member_count})",
                partial(self._open_group, group.id, group.name),
            )
        if groups:
            self._groups_menu.addSeparator()
        self._groups_menu.addAction("Manage groups…", self._open_groups)

    def _open_group(self, group_id, group_name) -> None:
        from ui.group_view_dialog import GroupViewDialog
        GroupViewDialog(group_id, group_name, parent=self).exec()

    def _open_groups(self) -> None:
        from ui.groups_dialog import GroupsDialog
        GroupsDialog(self).exec()

    # --- shopping cart (Phase 38) ------------------------------------------

    def _populate_cart_menu(self) -> None:
        self._cart_menu.clear()
        count = repo.cart_count()
        self._cart_menu.addAction(f"Open cart  ({count})", self._open_cart)
        self._cart_menu.addSeparator()
        clear = self._cart_menu.addAction("Clear cart", self._clear_cart)
        clear.setEnabled(count > 0)

    def _open_cart(self) -> None:
        from ui.cart_dialog import CartDialog
        self._cart_dialog = CartDialog(self)
        try:
            self._cart_dialog.exec()
        finally:
            self._cart_dialog = None

    def _refresh_cart_if_open(self) -> None:
        """If the cart is open, re-pull prices so a just-finished refresh shows
        immediately (quantities are persisted, so they're preserved)."""
        dialog = self._cart_dialog
        if dialog is not None and dialog.isVisible():
            dialog.reload_prices()

    def _clear_cart(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear cart",
            "Remove all items from the cart? The products themselves stay tracked.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            repo.clear_cart()
            self.statusBar().showMessage("Cart cleared")

    def _add_to_cart(self, product_id) -> None:
        added = repo.add_to_cart(product_id)
        self.statusBar().showMessage("Added to cart" if added else "Already in cart")

    def _remove_from_cart(self, product_id) -> None:
        repo.remove_from_cart(product_id)
        self.statusBar().showMessage("Removed from cart")

    # --- discovery: search the product on Google (Phase 35) ---------------

    def _open_google(self, query: str) -> None:
        QDesktopServices.openUrl(QUrl("https://www.google.com/search?q=" + quote_plus(query)))

    def _search_google(self, product_id) -> None:
        """Open a Google search for the product so the user can find it (in
        stock / cheaper) on other sites — robust, instant, no scraping."""
        product = repo.get_product(product_id)
        if product is None:
            return
        self._open_google(product.name or product.url)

    def _show_row_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        product_id = next((pid for pid, r in self._row_for_product.items() if r == row), None)
        if product_id is None:
            return
        groups = repo.list_groups()
        current = {g.id for g in repo.groups_for_product(product_id)}

        menu = QMenu(self)
        menu.addAction("Search on Google…", partial(self._search_google, product_id))
        # Complementary suggestions for this product's category (Phase 36).
        name_item = self.table.item(row, COL_NAME)
        suggestions = complement_terms(name_item.text() if name_item else "")
        if suggestions:
            sug_menu = menu.addMenu("You might also need")
            for term in suggestions:
                sug_menu.addAction(f"Search: {term}", partial(self._open_google, term))
        menu.addSeparator()
        if product_id in repo.cart_product_ids():
            menu.addAction("Remove from cart", partial(self._remove_from_cart, product_id))
        else:
            menu.addAction("Add to cart", partial(self._add_to_cart, product_id))
        menu.addSeparator()
        add_menu = menu.addMenu("Add to group")
        for group in groups:
            if group.id in current:
                continue
            add_menu.addAction(group.name, partial(self._add_to_group, group.id, product_id))
        if add_menu.actions():
            add_menu.addSeparator()
        add_menu.addAction("New group…", partial(self._add_to_new_group, product_id))

        if current:
            remove_menu = menu.addMenu("Remove from group")
            for group in groups:
                if group.id in current:
                    remove_menu.addAction(
                        group.name, partial(self._remove_from_group, group.id, product_id)
                    )
        menu.addSeparator()
        menu.addAction("Manage groups…", self._open_groups)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_to_group(self, group_id, product_id) -> None:
        repo.add_to_group(group_id, product_id)
        self.statusBar().showMessage("Added to group")

    def _add_to_new_group(self, product_id) -> None:
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if ok and name.strip():
            group = repo.create_group(name.strip())
            repo.add_to_group(group.id, product_id)
            self.statusBar().showMessage(f"Added to new group '{name.strip()}'")

    def _remove_from_group(self, group_id, product_id) -> None:
        repo.remove_from_group(group_id, product_id)
        self.statusBar().showMessage("Removed from group")

    def _open_settings(self) -> None:
        SettingsDialog(self).exec()
        # Theme may have changed — rebuild rows so the link color follows it.
        self.reload()
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
        dialog = EditProductDialog(
            product.name or "", product.url, getattr(product, "target_price", None), parent=self
        )
        if dialog.exec() == EditProductDialog.DialogCode.Accepted:
            name, url, target = dialog.values()
            repo.update_product(product_id, name=name, url=url, target_price=target)
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
