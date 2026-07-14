"""Persistence operations — the DB-backed replacement for the old storage.py.

The UI and the background scheduler call these functions; they never touch the
ORM session directly.
"""
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import func, select

from .currency import normalize_currency
from .db import session_scope
from .models import CartItem, Group, GroupMember, PriceHistory, Product, utcnow


def _retailer_from_url(url: str) -> str:
    """Best-effort store identifier from a product URL (refined in Phase 2)."""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if "amazon." in host:
        return "amazon"
    return host or "unknown"


def _canonical_url(url: str) -> str:
    """Compare-friendly form (no scheme/www/query/trailing slash) for matching a
    re-added URL to a previously soft-deleted product."""
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return f"{host}{parsed.path.rstrip('/')}"


def add_product(
    url: str,
    name: Optional[str] = None,
    price: Optional[float] = None,
    currency: str = "",
    stock: Optional[str] = None,
    retailer: Optional[str] = None,
    user_id: Optional[int] = None,
    image_url: Optional[str] = None,
) -> Product:
    """Insert a product and seed its first price-history row if we already have
    data. If the same URL was removed before (soft-deleted), revive that record
    instead so its price history comes back. The returned object carries a
    transient ``revived`` flag."""
    with session_scope() as session:
        target = _canonical_url(url)
        revived = next(
            (p for p in session.scalars(select(Product).where(Product.deleted_at.is_not(None)))
             if _canonical_url(p.url) == target),
            None,
        )
        next_position = (session.scalar(select(func.max(Product.position))) or 0) + 1

        if revived is not None:
            revived.deleted_at = None          # back on the list, history intact
            revived.url = url
            revived.retailer = retailer or _retailer_from_url(url)
            revived.currency = normalize_currency(currency)
            revived.position = next_position   # move to the end
            if name is not None:
                revived.name = name
            if price is not None:
                revived.last_price = price
            if stock is not None:
                revived.last_stock = stock
            if image_url:
                revived.image_url = image_url
            if price is not None or stock is not None:
                revived.last_checked = utcnow()
                session.add(PriceHistory(product_id=revived.id, price=price, stock=stock))
            revived.revived = True
            return revived

        product = Product(
            url=url,
            name=name,
            currency=normalize_currency(currency),
            retailer=retailer or _retailer_from_url(url),
            last_price=price,
            last_stock=stock,
            image_url=image_url,
            user_id=user_id,
            position=next_position,
            last_checked=utcnow() if (price is not None or stock is not None) else None,
        )
        session.add(product)
        session.flush()  # assigns product.id

        if price is not None or stock is not None:
            session.add(PriceHistory(product_id=product.id, price=price, stock=stock))

        product.revived = False
        return product


def list_products(user_id: Optional[int] = None) -> List[Product]:
    with session_scope() as session:
        stmt = (
            select(Product)
            .where(Product.deleted_at.is_(None))  # hide soft-deleted products
            .order_by(Product.position, Product.created_at)
        )
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


_UNSET = object()  # sentinel: "argument not provided" (vs. None = clear the value)


def update_product(
    product_id: int,
    name: Optional[str] = None,
    url: Optional[str] = None,
    target_price=_UNSET,
) -> Optional[Product]:
    """Edit user-editable fields (name / URL / target price)."""
    with session_scope() as session:
        product = session.get(Product, product_id)
        if product is None:
            return None
        if name is not None:
            product.name = name
        if url is not None:
            product.url = url
            product.retailer = _retailer_from_url(url)
        if target_price is not _UNSET:
            product.target_price = target_price  # float to set, None to clear
        return product


def delete_product(product_id: int) -> bool:
    """Soft delete: hide the product but keep its row + price history, so re-adding
    the same URL later revives it (see add_product)."""
    with session_scope() as session:
        product = session.get(Product, product_id)
        if product is None:
            return False
        product.deleted_at = utcnow()
        return True


def apply_scrape_result(
    product_id: int,
    name: Optional[str] = None,
    price: Optional[float] = None,
    currency: Optional[str] = None,
    stock: Optional[str] = None,
    image_url: Optional[str] = None,
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
            product.currency = normalize_currency(currency)
        if price is not None:
            product.last_price = price
        if stock is not None:
            product.last_stock = stock
        if image_url:
            product.image_url = image_url
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


def recent_history(since: datetime) -> dict:
    """All price points since `since`, grouped by product id (one query).
    Used to compute price trends without a per-product query (Phase 37)."""
    with session_scope() as session:
        stmt = (
            select(PriceHistory.product_id, PriceHistory.captured_at, PriceHistory.price)
            .where(PriceHistory.captured_at >= since)
        )
        result: dict = {}
        for product_id, captured_at, price in session.execute(stmt):
            result.setdefault(product_id, []).append((captured_at, price))
        return result


# --- groups (Phase 34) ----------------------------------------------------

def create_group(name: str, user_id: Optional[int] = None) -> Group:
    with session_scope() as session:
        group = Group(name=name, user_id=user_id)
        session.add(group)
        session.flush()
        group.member_count = 0
        return group


def list_groups(user_id: Optional[int] = None) -> List[Group]:
    with session_scope() as session:
        stmt = select(Group).order_by(Group.created_at)
        if user_id is not None:
            stmt = stmt.where(Group.user_id == user_id)
        groups = list(session.scalars(stmt))
        for group in groups:
            group.member_count = session.scalar(
                select(func.count()).select_from(GroupMember)
                .where(GroupMember.group_id == group.id)
            ) or 0
        return groups


def rename_group(group_id: int, name: str) -> Optional[Group]:
    with session_scope() as session:
        group = session.get(Group, group_id)
        if group is None:
            return None
        group.name = name
        return group


def delete_group(group_id: int) -> bool:
    with session_scope() as session:
        group = session.get(Group, group_id)
        if group is None:
            return False
        session.delete(group)  # cascades to group_members
        return True


def add_to_group(group_id: int, product_id: int) -> bool:
    """Add a product to a group; returns False if it was already a member."""
    with session_scope() as session:
        exists = session.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.product_id == product_id
            )
        )
        if exists is not None:
            return False
        session.add(GroupMember(group_id=group_id, product_id=product_id))
        return True


def remove_from_group(group_id: int, product_id: int) -> bool:
    with session_scope() as session:
        member = session.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.product_id == product_id
            )
        )
        if member is None:
            return False
        session.delete(member)
        return True


def group_members(group_id: int) -> List[Product]:
    with session_scope() as session:
        stmt = (
            select(Product)
            .join(GroupMember, GroupMember.product_id == Product.id)
            .where(GroupMember.group_id == group_id, Product.deleted_at.is_(None))
            .order_by(Product.position, Product.created_at)
        )
        return list(session.scalars(stmt))


def groups_for_product(product_id: int) -> List[Group]:
    with session_scope() as session:
        stmt = (
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.product_id == product_id)
            .order_by(Group.created_at)
        )
        return list(session.scalars(stmt))


# --- shopping cart (Phase 38) ---------------------------------------------

def add_to_cart(product_id: int, quantity: int = 1, user_id: Optional[int] = None) -> bool:
    """Add a product to the cart; returns False if it was already in the cart."""
    with session_scope() as session:
        exists = session.scalar(select(CartItem).where(CartItem.product_id == product_id))
        if exists is not None:
            return False
        session.add(CartItem(product_id=product_id, quantity=max(1, quantity), user_id=user_id))
        return True


def set_cart_quantity(product_id: int, quantity: int) -> bool:
    """Set a cart item's quantity; quantity <= 0 removes it. False if not in cart."""
    with session_scope() as session:
        item = session.scalar(select(CartItem).where(CartItem.product_id == product_id))
        if item is None:
            return False
        if quantity <= 0:
            session.delete(item)
        else:
            item.quantity = quantity
        return True


def remove_from_cart(product_id: int) -> bool:
    with session_scope() as session:
        item = session.scalar(select(CartItem).where(CartItem.product_id == product_id))
        if item is None:
            return False
        session.delete(item)
        return True


def clear_cart() -> None:
    with session_scope() as session:
        for item in session.scalars(select(CartItem)):
            session.delete(item)


def cart_products() -> List[Product]:
    """Products in the cart, each annotated with `.quantity`, in display order."""
    with session_scope() as session:
        rows = session.execute(
            select(Product, CartItem.quantity)
            .join(CartItem, CartItem.product_id == Product.id)
            .where(Product.deleted_at.is_(None))
            .order_by(Product.position, Product.created_at)
        ).all()
        products = []
        for product, quantity in rows:
            product.quantity = quantity
            products.append(product)
        return products


def cart_product_ids() -> set:
    """Set of product ids currently in the cart (for menu state)."""
    with session_scope() as session:
        return set(session.scalars(select(CartItem.product_id)))


def cart_count() -> int:
    """Number of distinct products in the cart."""
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(CartItem)) or 0
