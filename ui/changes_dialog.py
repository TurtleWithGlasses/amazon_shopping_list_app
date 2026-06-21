"""Report window listing the price/stock changes since the last session.

Shown once at startup (Phase 18) when the launch refresh detects changes; rows
are pre-formatted (product, price, stock) so the dialog stays presentation-only.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class StartupChangesDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Changes since last session")
        self.resize(680, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"{len(rows)} product(s) changed while you were away:"
        ))

        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["Product", "Price", "Stock"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for r, (name, price_text, stock_text) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(name))
            price_item = QTableWidgetItem(price_text)
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, 1, price_item)
            stock_item = QTableWidgetItem(stock_text)
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, 2, stock_item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
