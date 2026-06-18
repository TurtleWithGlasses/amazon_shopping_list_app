"""Price-history chart with a selectable timescale."""
from datetime import timezone

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from core import repository as repo
from services.timescales import DEFAULT_TIMESCALE, TIMESCALE_LABELS, since_for


class GraphDialog(QDialog):
    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle(f"Price history — {product.name or product.url}")
        self.resize(760, 440)

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Timescale:"))
        self.timescale = QComboBox()
        self.timescale.addItems(TIMESCALE_LABELS)
        self.timescale.setCurrentText(DEFAULT_TIMESCALE)
        controls.addWidget(self.timescale)
        controls.addStretch(1)
        layout.addLayout(controls)

        axis = pg.DateAxisItem(orientation="bottom")
        self.plot = pg.PlotWidget(axisItems={"bottom": axis})
        self.plot.setBackground("w")
        self.plot.setLabel("left", "Price", units=product.currency or "")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.plot)

        self.empty_label = QLabel("No price history for this timescale yet.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.timescale.currentTextChanged.connect(self._redraw)
        self._redraw()

    def _redraw(self) -> None:
        since = since_for(self.timescale.currentText())
        history = repo.get_price_history(self.product.id, since=since)
        points = [(h.captured_at, h.price) for h in history if h.price is not None]

        self.plot.clear()
        if not points:
            self.plot.hide()
            self.empty_label.show()
            return

        self.empty_label.hide()
        self.plot.show()
        # captured_at is naive UTC; treat as UTC for the timestamp axis
        xs = [t.replace(tzinfo=timezone.utc).timestamp() for t, _ in points]
        ys = [price for _, price in points]
        self.plot.plot(
            xs, ys,
            pen=pg.mkPen("#1f77b4", width=2),
            symbol="o",
            symbolSize=7,
            symbolBrush="#1f77b4",
        )
