"""Persistence operations — the DB-backed replacement for the old storage.py.

The UI and the background scheduler call these functions; they never touch the
ORM session directly.
"""
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import func, select

from .db import session_scope
from .models import PriceHistory, Product, utcnow


def _retailer_from_url(url: str) -> str:
    """Best-effort store identifier from a product URL (refined in Phase 2)."""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if "amazon." in host:
        return "amazon"
    return host or "unknown"


def add_product(
    url: str,
    name: Optional[str] = None,
    price: Optional[float] = None,
    currency: str = "",
    stock: Optional[str] = None,
    retailer: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Product:
    """Insert a product and seed its first price-history row if we already have data."""
    with session_scope() as session:
        next_position = (session.scalar(select(func.max(Product.position))) or 0) + 1
        product = Product(
            url=url,
            name=name,
            currency=currency,
            retailer=retailer or _retailer_from_url(url),
            last_price=price,
            last_stock=stock,
            user_id=user_id,
            position=next_position,
            last_checked=utcnow() if (price is not None or stock is not None) else None,
        )
        session.add(product)
        session.flush()  # assigns product.id

        if price is not None or stock is not None:
            session.add(PriceHistory(product_id=product.id, price=price, stock=stock))

        return product


def list_products(user_id: Optional[int] = None) -> List[Product]:
    with session_scope() as session:
        stmt = select(Product).order_by(Product.position, Product.created_at)
        if user_id is not None:
            stmt = stmt.where(Product.user_id == user_id)
        return list(session.scalars(stmt))


def reorder_products(ordered_ids: List[int]) -> None:
    """Persist a new manual order: position = index in the given id list."""
    with session_scope() as session:
        for index, product_id in enumerate(ordered_ids):
            product = session.get(Product, product_id)
            if product is not None:
                product.position = index


def get_product(product_id: int) -> Optional[Product]:
    with session_scope() as session:
        return session.get(Product, product_id)


def update_product(
    product_id: int,
    name: Optional[str] = None,
    url: Optional[str] = None,
) -> Optional[Product]:
    """Edit user-editable fields (name / URL)."""
    with session_scope() as session:
        product = session.get(Product, product_id)
        if product is None:
            return None
        if name is not None:
            product.name = name
        if url is not None:
            product.url = url
            product.retailer = _retailer_from_url(url)
        return product


def delete_product(product_id: int) -> bool:
    with session_scope() as session:
        product = session.get(Product, product_id)
        if product is None:
            return False
        session.delete(product)  # cascades to price_history
        return True


def apply_scrape_result(
    product_id: int,
    name: Optional[str] = None,
    price: Optional[float] = None,
    currency: Optional[str] = None,
    stock: Optional[str] = None,
) -> Optional[Product]:
    """Update a product's latest values and compute price/stock change flags.

    Called by the 5-minute refresh. Does NOT write price history — that's the
    separate hourly snapshot (record_price_snapshot).
    """
    with session_scope() as session:
        product = session.get(Product, product_id)
        if product is None:
            return None

        price_changed = (
            price is not None and product.last_price is not None and price != product.last_price
        )
        stock_changed = (
            stock is not None and product.last_stock is not None and stock != product.last_stock
        )

        if price_changed:
            product.prev_price = product.last_price
        if stock_changed:
            product.prev_stock = product.last_stock

        product.price_changed = price_changed
        product.stock_changed = stock_changed

        if name:
            product.name = name
        if currency is not None:
            product.currency = currency
        if price is not None:
            product.last_price = price
        if stock is not None:
            product.last_stock = stock
        product.last_checked = utcnow()

        return product


def record_price_snapshot(
    product_id: int,
    price: Optional[float] = None,
    stock: Optional[str] = None,
) -> Optional[PriceHistory]:
    """Append an hourly price/stock data point for charting and export."""
    with session_scope() as session:
        if session.get(Product, product_id) is None:
            return None
        entry = PriceHistory(product_id=product_id, price=price, stock=stock)
        session.add(entry)
        session.flush()
        return entry


def get_price_history(
    product_id: int,
    since: Optional[datetime] = None,
) -> List[PriceHistory]:
    """History rows for one product, oldest first, optionally limited by timescale."""
    with session_scope() as session:
        stmt = select(PriceHistory).where(PriceHistory.product_id == product_id)
        if since is not None:
            stmt = stmt.where(PriceHistory.captured_at >= since)
        stmt = stmt.order_by(PriceHistory.captured_at)
        return list(session.scalars(stmt))
