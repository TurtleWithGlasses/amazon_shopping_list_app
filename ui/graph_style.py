"""Theme-aware styling for pyqtgraph plots (Phase 39).

The price-history and group graphs used to hardcode a white background and fixed
axis/grid colors, so they clashed on the dark / Stitch / Material themes (a white
chart in a dark window). These helpers drive pyqtgraph styling from the active
theme tokens (ui/theme.py) instead, and are re-applied each time a graph opens.
"""
import pyqtgraph as pg

from ui.theme import active_theme

# Per-line palette for multi-series (group) graphs — distinct hues chosen to stay
# legible on both light and dark surfaces.
LINE_COLORS = ["#4f8ef7", "#e3534a", "#33b864", "#b483f0",
               "#ff9f40", "#26c6da", "#a1887f", "#ec6fb8"]

# Hover accent that stands out on any background (kept theme-independent).
HOVER_COLOR = "#e8830c"


def style_plot(plot) -> dict:
    """Apply the active theme's surface / text / grid colors to a PlotWidget and
    return the theme map, so callers can pick line/legend colors that match."""
    t = active_theme()
    plot.setBackground(t["base"])
    for name in ("left", "bottom"):
        axis = plot.getAxis(name)
        axis.setPen(pg.mkPen(t["border"]))           # axis line + grid
        axis.setTextPen(pg.mkPen(t["subtext"]))      # tick labels
    plot.showGrid(x=True, y=True, alpha=0.25)
    return t
