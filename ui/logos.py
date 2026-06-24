"""Per-row retailer logos for the product table (roadmap Phase 23).

Maps a product to a bundled logo in ``assets/logos/`` keyed by the scraper
adapter name (``amazon``, ``n11``, ``hepsiburada``, ``itopya``, ``sinerji``,
``incehesap``, ``aliexpress``) or, for sites without a dedicated adapter, the
domain word (e.g. ``teknosa.com`` -> ``teknosa``), falling back to ``generic``.
Scaled pixmaps are cached per (key, box) so repeated rows are cheap.
"""
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from core.scraping.registry import get_adapter

_LOGO_DIR = Path(__file__).resolve().parent.parent / "assets" / "logos"
_FALLBACK = "generic"
_TLDS = {"com", "net", "org", "co", "gen", "tr", "gov", "edu"}
_cache: dict[tuple, QPixmap] = {}


def _domain_key(url: str) -> str:
    """Domain word from a URL: www.teknosa.com -> 'teknosa', tr.aliexpress.com
    -> 'aliexpress' (drop a leading www and trailing TLD parts)."""
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    parts = [p for p in host.split(".") if p]
    while len(parts) > 1 and parts[-1] in _TLDS:
        parts.pop()
    return parts[-1] if parts else ""


def logo_key(product) -> str:
    """Logo filename stem for a product, or ``generic``."""
    retailer = (getattr(product, "retailer", "") or "").strip().lower()
    if retailer and (_LOGO_DIR / f"{retailer}.png").exists():
        return retailer
    url = getattr(product, "url", "") or ""
    adapter = get_adapter(url)
    if adapter and adapter.name != _FALLBACK and (_LOGO_DIR / f"{adapter.name}.png").exists():
        return adapter.name
    # Sites handled by the generic adapter: match a bundled logo by domain word.
    site = _domain_key(url)
    if site and (_LOGO_DIR / f"{site}.png").exists():
        return site
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
