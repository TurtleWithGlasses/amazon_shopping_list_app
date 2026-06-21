"""Per-row retailer logos for the product table (roadmap Phase 23).

Maps a product to a bundled logo in ``assets/logos/`` keyed by the scraper
adapter name (``amazon``, ``n11``, ``hepsiburada``, ``itopya``, ``sinerji``,
``incehesap``, ``aliexpress``), falling back to ``generic`` for anything else.
Scaled pixmaps are cached per (key, box) so repeated rows are cheap.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from core.scraping.registry import get_adapter

_LOGO_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"
_FALLBACK = "generic"
_cache: dict[tuple, QPixmap] = {}


def logo_key(product) -> str:
    """Logo filename stem for a product (adapter name), or ``generic``."""
    retailer = (getattr(product, "retailer", "") or "").strip().lower()
    if retailer and (_LOGO_DIR / f"{retailer}.png").exists():
        return retailer
    adapter = get_adapter(getattr(product, "url", "") or "")
    if adapter and (_LOGO_DIR / f"{adapter.name}.png").exists():
        return adapter.name
    return _FALLBACK


def logo_pixmap(product, max_w: int, max_h: int) -> QPixmap | None:
    """A smoothly scaled logo that fits within ``max_w`` x ``max_h`` (aspect kept)."""
    key = logo_key(product)
    cache_key = (key, max_w, max_h)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    path = _LOGO_DIR / f"{key}.png"
    if not path.exists():
        return None
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    pm = pm.scaled(
        max_w, max_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _cache[cache_key] = pm
    return pm
