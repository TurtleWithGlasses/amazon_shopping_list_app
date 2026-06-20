"""Price / stock history chart with a metric toggle and selectable timescale."""
from datetime import datetime, timezone

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core import datastore as repo
from services.stock import LEVEL_LABELS, classify_stock
from services.timescales import DEFAULT_TIMESCALE, TIMESCALE_LABELS, since_for

_LINE = pg.mkPen("#1f77b4", width=2)
_BRUSH = "#1f77b4"


class GraphDialog(QDialog):
    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.product = product
        self._metric = "price"
        self.setWindowTitle(f"History — {product.name or product.url}")
        self.resize(760, 460)

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        # Metric toggle: Price | Stock
        self.price_button = QPushButton("Price")
        self.stock_button = QPushButton("Stock")
        group = QButtonGroup(self)
        group.setExclusive(True)
        for button, metric in ((self.price_button, "price"), (self.stock_button, "stock")):
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, m=metric: self._set_metric(m))
            group.addButton(button)
            controls.addWidget(button)
        self.price_button.setChecked(True)

        controls.addSpacing(16)
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
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.plot)

        self.empty_label = QLabel("No history for this timescale yet.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.timescale.currentTextChanged.connect(self._redraw)
        self._redraw()

    def _set_metric(self, metric: str) -> None:
        self._metric = metric
        self._redraw()

    def _history(self):
        since = since_for(self.timescale.currentText())
        return repo.get_price_history(self.product.id, since=since)

    @staticmethod
    def _ts(captured_at) -> float:
        return captured_at.replace(tzinfo=timezone.utc).timestamp()

    def _show_empty(self, is_empty: bool) -> None:
        self.empty_label.setVisible(is_empty)
        self.plot.setVisible(not is_empty)

    def _redraw(self) -> None:
        if self._metric == "stock":
            self._plot_stock()
        else:
            self._plot_price()

    @staticmethod
    def _fmt_time(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%d %b %Y %H:%M")

    def _add_hover_points(self, xs, ys, tips) -> None:
        """Hoverable markers showing `tips[i]` when the cursor is over a point."""
        scatter = pg.ScatterPlotItem(
            x=xs, y=ys, size=9,
            brush=pg.mkBrush(_BRUSH), pen=pg.mkPen("w", width=1),
            hoverable=True, hoverSize=13, hoverBrush=pg.mkBrush("#e8830c"),
            data=tips, tip=lambda x, y, data: data,
        )
        self.plot.addItem(scatter)

    def _plot_price(self) -> None:
        points = [(self._ts(h.captured_at), h.price)
                  for h in self._history() if h.price is not None]
        self.plot.clear()
        # Reset to a numeric axis (in case we were showing stock categories).
        self.plot.getAxis("left").setTicks(None)
        self.plot.setLabel("left", "Price", units=self.product.currency or "")
        self.plot.enableAutoRange(axis="y")
        if not points:
            self._show_empty(True)
            return
        self._show_empty(False)
        xs = [t for t, _ in points]
        ys = [p for _, p in points]
        self.plot.plot(xs, ys, pen=_LINE)
        cur = self.product.currency or ""
        tips = [f"{p:,.2f} {cur}".strip() + f"\n{self._fmt_time(t)}" for t, p in points]
        self._add_hover_points(xs, ys, tips)

    def _plot_stock(self) -> None:
        points = []
        for h in self._history():
            level, _qty = classify_stock(h.stock or "")
            if level is None:
                continue  # unknown → gap
            points.append((self._ts(h.captured_at), level, (h.stock or "").strip()))
        self.plot.clear()
        # Categorical Y axis: Out / Limited / In stock.
        self.plot.getAxis("left").setTicks(
            [[(level, label) for level, label in LEVEL_LABELS.items()]]
        )
        self.plot.setLabel("left", "Availability")
        if not points:
            self._show_empty(True)
            return
        self._show_empty(False)
        # Right-continuous step line: hold each level until the next sample.
        step_x, step_y = [], []
        for i, (t, level, _txt) in enumerate(points):
            step_x.append(t)
            step_y.append(level)
            if i + 1 < len(points):
                step_x.append(points[i + 1][0])
                step_y.append(level)
        self.plot.plot(step_x, step_y, pen=_LINE)
        xs = [t for t, _, _ in points]
        ys = [lv for _, lv, _ in points]
        tips = [f"{txt or LEVEL_LABELS.get(lv, '')}\n{self._fmt_time(t)}"
                for t, lv, txt in points]
        self._add_hover_points(xs, ys, tips)
        self.plot.setYRange(-0.2, 2.2)
