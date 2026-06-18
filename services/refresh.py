"""Apply a scrape result to a product and log a history point.

Used by the manual "Refresh All" button now, and by the Phase 4 scheduler later.
"""
from typing import Optional

from core import datastore as repo
from core.scraping import ProductData


def apply_and_snapshot(product_id: int, data: ProductData) -> Optional[object]:
    """Update latest price/stock (+ change flags) and append a history point."""
    if not data.ok:
        return None
    product = repo.apply_scrape_result(
        product_id,
        name=data.name,
        price=data.price,
        currency=data.currency,
        stock=data.stock,
    )
    if product is not None:
        repo.record_price_snapshot(product_id, price=product.last_price, stock=product.last_stock)
    return product
