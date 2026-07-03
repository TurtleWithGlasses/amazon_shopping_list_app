"""In-app notifications center (Phase 40): a window listing recent changes.

Presentation-only — it receives pre-formatted rows (when · product · change) and
a clear callback, mirroring StartupChangesDialog. Newest first. Columns are
user-resizable, and the window size + column widths persist across opens.
"""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

_GEOMETRY_KEY = "notif_center/geometry"
_HEADER_KEY = "notif_center/header_state_v1"
# Sensible first-run column widths (When, Product, Change).
_DEFAULT_WIDTHS = (140, 560, 360)


class NotificationCenterDialog(QDialog):
    def __init__(self, rows, on_clear, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notifications")
        self._on_clear = on_clear

        layout = QVBoxLayout(self)
        if rows:
            layout.addWidget(QLabel(f"{len(rows)} recent change(s), newest first:"))
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
        for r, (when, product, change) in enumerate(rows):
            when_item = QTableWidgetItem(when)
            when_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 0, when_item)
            self.table.setItem(r, 1, QTableWidgetItem(product))
            self.table.setItem(r, 2, QTableWidgetItem(change))

        # All columns user-resizable; a horizontal scrollbar appears when the
        # content is wider than the viewport (long product names / change text).
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
        # Single funnel for accept / reject / window-close: persist before closing.
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
