"""Price trend over a window (Phase 37).

Given a product's price points within a window (e.g. the last 7 days), classify
the tendency as rising / falling / stable using a least-squares slope (robust to
a single blip), and report the line's total change over the span as a percent.
No ML; reads the price history the app already stores.
"""
from typing import List, Optional, Tuple

STABLE_BAND = 1.0  # |%| below this over the window counts as "stable"


def price_trend(points, stable_band: float = STABLE_BAND) -> Tuple[str, Optional[float]]:
    """Return (state, percent_change) where state is
    'falling' | 'rising' | 'stable' | 'unknown'. `points` is an iterable of
    (timestamp, price); timestamp may be a datetime or a number."""
    pts = [(t, float(p)) for t, p in points if p is not None and t is not None]
    if len(pts) < 2:
        return ("unknown", None)
    pts.sort(key=lambda tp: tp[0])
    # x as seconds from the first point (avoids huge absolute timestamps)
    t0 = pts[0][0]
    xs: List[float] = [_to_seconds(t - t0) for t, _ in pts]
    ys: List[float] = [p for _, p in pts]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0 or mean_y <= 0:
        return ("unknown", None)
    slope = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / denom
    span = xs[-1] - xs[0]
    pct = (slope * span) / mean_y * 100.0  # line's total change over the span, % of mean
    if abs(pct) < stable_band:
        return ("stable", pct)
    return ("falling" if pct < 0 else "rising", pct)


def _to_seconds(delta) -> float:
    """Seconds from a timedelta, or the value itself if it's already numeric."""
    total = getattr(delta, "total_seconds", None)
    return total() if callable(total) else float(delta)
