"""In-app notifications center (Phase 40): a window listing recent changes.

Presentation-only — it receives pre-formatted rows (when · product · change) and
a clear callback, mirroring StartupChangesDialog. Newest first.
"""
from PySide6.QtCore import Qt
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


class NotificationCenterDialog(QDialog):
    def __init__(self, rows, on_clear, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Notifications")
        self.resize(720, 460)
        self._on_clear = on_clear

        layout = QVBoxLayout(self)
        if rows:
            layout.addWidget(QLabel(f"{len(rows)} recent change(s), newest first:"))
        else:
            layout.addWidget(QLabel(
                "No notifications yet. Price and stock changes from each refresh "
                "will appear here."
            ))

        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["When", "Product", "Change"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setWordWrap(False)
        for r, (when, product, change) in enumerate(rows):
            when_item = QTableWidgetItem(when)
            when_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, 0, when_item)
            table.setItem(r, 1, QTableWidgetItem(product))
            table.setItem(r, 2, QTableWidgetItem(change))

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table, 1)

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

    def _clear(self) -> None:
        confirm = QMessageBox.question(
            self, "Clear notifications", "Remove all notifications from the list?"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._on_clear()
            self.accept()
