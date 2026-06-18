"""Adapter registry: route a product URL to the retailer that can scrape it.

Adding a new store later is just: write an adapter, then `register(MyAdapter())`.
"""
from typing import List, Optional

from .amazon import AmazonAdapter
from .base import ProductData, RetailerAdapter

# Registration order = match priority. Amazon is the only adapter for now.
_ADAPTERS: List[RetailerAdapter] = [
    AmazonAdapter(),
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
