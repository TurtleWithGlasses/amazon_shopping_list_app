"""Price history chart with a selectable timescale and hover tooltips."""
from datetime import datetime, timezone

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout

from core import datastore as repo
from services.timescales import DEFAULT_TIMESCALE, TIMESCALE_LABELS, since_for

_LINE = pg.mkPen("#1f77b4", width=2)
_BRUSH = "#1f77b4"


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

    def _history(self):
        since = since_for(self.timescale.currentText())
        return repo.get_price_history(self.product.id, since=since)

    @staticmethod
    def _ts(captured_at) -> float:
        return captured_at.replace(tzinfo=timezone.utc).timestamp()

    @staticmethod
    def _fmt_time(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")

    def _add_hover_points(self, xs, ys, tips) -> None:
        scatter = pg.ScatterPlotItem(
            x=xs, y=ys, size=9,
            brush=pg.mkBrush(_BRUSH), pen=pg.mkPen("w", width=1),
            hoverable=True, hoverSize=13, hoverBrush=pg.mkBrush("#e8830c"),
            data=tips, tip=lambda x, y, data: data,
        )
        self.plot.addItem(scatter)

    def _redraw(self) -> None:
        points = [(self._ts(h.captured_at), h.price)
                  for h in self._history() if h.price is not None]
        self.plot.clear()
        if not points:
            self.empty_label.setVisible(True)
            self.plot.setVisible(False)
            return
        self.empty_label.setVisible(False)
        self.plot.setVisible(True)
        xs = [t for t, _ in points]
        ys = [p for _, p in points]
        self.plot.plot(xs, ys, pen=_LINE)
        cur = self.product.currency or ""
        tips = [f"{p:,.2f} {cur}".strip() + f"\n{self._fmt_time(t)}" for t, p in points]
        self._add_hover_points(xs, ys, tips)
