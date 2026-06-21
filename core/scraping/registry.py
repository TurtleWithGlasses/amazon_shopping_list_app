"""Adapter registry: route a product URL to the retailer that can scrape it.

Adding a new store later is just: write an adapter, then `register(MyAdapter())`.
"""
from typing import List, Optional

from .aliexpress import AliExpressAdapter
from .amazon import AmazonAdapter
from .base import ProductData, RetailerAdapter
from .generic import GenericAdapter
from .hepsiburada import HepsiburadaAdapter
from .itopya import ItopyaAdapter
from .n11 import N11Adapter
from .sinerji import SinerjiAdapter

# Registration order = match priority. Site-specific adapters first; the generic
# structured-data adapter is the catch-all for every other site.
_ADAPTERS: List[RetailerAdapter] = [
    AmazonAdapter(),
    N11Adapter(),
    HepsiburadaAdapter(),
    AliExpressAdapter(),
    ItopyaAdapter(),
    SinerjiAdapter(),
    GenericAdapter(),
]


def register(adapter: RetailerAdapter) -> None:
    _ADAPTERS.append(adapter)


def get_adapter(url: str) -> Optional[RetailerAdapter]:
    return next((a for a in _ADAPTERS if a.matches(url)), None)


def supported_retailers() -> List[str]:
    return [a.name for a in _ADAPTERS]


def scrape(url: str) -> ProductData:
    """Scrape any supported product URL into a ProductData."""
    url = (url or "").strip()
    adapter = get_adapter(url)
    if adapter is None:
        return ProductData(
            url=url,
            error="Unsupported site. Currently only Amazon URLs are supported.",
        )
    return adapter.scrape(url)
