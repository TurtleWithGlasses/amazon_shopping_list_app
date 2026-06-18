"""Cloud (Supabase Postgres) repository.

Mirrors core/repository.py's API so it can be swapped in via core/datastore.py
after login. Row-level security scopes every query to the logged-in user; we
also set user_id explicitly on insert to satisfy the RLS check constraint.

Returns lightweight dataclasses with the same attribute names the UI expects.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from .auth import current_user_id
from .client import get_client


@dataclass
class CloudProduct:
    id: int
    url: str
    retailer: str
    name: Optional[str]
    currency: str
    last_price: Optional[float]
    last_stock: Optional[str]
    prev_price: Optional[float]
    prev_stock: Optional[str]
    price_changed: bool
    stock_changed: bool
    position: int
    created_at: Optional[datetime]
    last_checked: Optional[datetime]


@dataclass
class CloudHistory:
    id: int
    product_id: int
    price: Optional[float]
    stock: Optional[str]
    captured_at: Optional[datetime]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _retailer_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if "amazon." in host:
        return "amazon"
    return host or "unknown"


def _to_product(row: dict) -> CloudProduct:
    return CloudProduct(
        id=row["id"],
        url=row["url"],
        retailer=row.get("retailer") or "",
        name=row.get("name"),
        currency=row.get("currency") or "",
        last_price=row.get("last_price"),
        last_stock=row.get("last_stock"),
        prev_price=row.get("prev_price"),
        prev_stock=row.get("prev_stock"),
        price_changed=bool(row.get("price_changed")),
        stock_changed=bool(row.get("stock_changed")),
        position=row.get("position") or 0,
        created_at=_parse_dt(row.get("created_at")),
        last_checked=_parse_dt(row.get("last_checked")),
    )


def _to_history(row: dict) -> CloudHistory:
    return CloudHistory(
        id=row["id"],
        product_id=row["product_id"],
        price=row.get("price"),
        stock=row.get("stock"),
        captured_at=_parse_dt(row.get("captured_at")),
    )


def _next_position(client) -> int:
    rows = client.table("products").select("position").order(
        "position", desc=True
    ).limit(1).execute().data
    return (rows[0]["position"] + 1) if rows and rows[0].get("position") is not None else 1


def add_product(url, name=None, price=None, currency="", stock=None,
                retailer=None, user_id=None) -> CloudProduct:
    client = get_client()
    payload = {
        "user_id": user_id or current_user_id(),
        "url": url,
        "retailer": retailer or _retailer_from_url(url),
        "name": name,
        "currency": currency,
        "last_price": price,
        "last_stock": stock,
        "position": _next_position(client),
        "last_checked": _now_iso() if (price is not None or stock is not None) else None,
    }
    row = client.table("products").insert(payload).execute().data[0]
    if price is not None or stock is not None:
        client.table("price_history").insert(
            {"product_id": row["id"], "price": price, "stock": stock}
        ).execute()
    return _to_product(row)


def list_products(user_id=None) -> List[CloudProduct]:
    # RLS already restricts to the current user.
    rows = (
        get_client().table("products").select("*")
        .order("position").order("created_at").execute().data
    )
    return [_to_product(r) for r in rows]


def reorder_products(ordered_ids: List[int]) -> None:
    client = get_client()
    for index, product_id in enumerate(ordered_ids):
        client.table("products").update({"position": index}).eq("id", product_id).execute()


def get_product(product_id) -> Optional[CloudProduct]:
    rows = get_client().table("products").select("*").eq("id", product_id).limit(1).execute().data
    return _to_product(rows[0]) if rows else None


def update_product(product_id, name=None, url=None) -> Optional[CloudProduct]:
    updates = {}
    if name is not None:
        updates["name"] = name
    if url is not None:
        updates["url"] = url
        updates["retailer"] = _retailer_from_url(url)
    if not updates:
        return get_product(product_id)
    rows = get_client().table("products").update(updates).eq("id", product_id).execute().data
    return _to_product(rows[0]) if rows else None


def delete_product(product_id) -> bool:
    rows = get_client().table("products").delete().eq("id", product_id).execute().data
    return bool(rows)


def apply_scrape_result(product_id, name=None, price=None, currency=None,
                        stock=None) -> Optional[CloudProduct]:
    client = get_client()
    rows = client.table("products").select("*").eq("id", product_id).limit(1).execute().data
    if not rows:
        return None
    row = rows[0]

    price_changed = price is not None and row.get("last_price") is not None and price != row["last_price"]
    stock_changed = stock is not None and row.get("last_stock") is not None and stock != row["last_stock"]

    updates = {
        "price_changed": price_changed,
        "stock_changed": stock_changed,
        "last_checked": _now_iso(),
    }
    if price_changed:
        updates["prev_price"] = row.get("last_price")
    if stock_changed:
        updates["prev_stock"] = row.get("last_stock")
    if name:
        updates["name"] = name
    if currency is not None:
        updates["currency"] = currency
    if price is not None:
        updates["last_price"] = price
    if stock is not None:
        updates["last_stock"] = stock

    updated = client.table("products").update(updates).eq("id", product_id).execute().data
    return _to_product(updated[0]) if updated else None


def record_price_snapshot(product_id, price=None, stock=None) -> Optional[CloudHistory]:
    rows = get_client().table("price_history").insert(
        {"product_id": product_id, "price": price, "stock": stock}
    ).execute().data
    return _to_history(rows[0]) if rows else None


def get_price_history(product_id, since=None) -> List[CloudHistory]:
    query = get_client().table("price_history").select("*").eq("product_id", product_id)
    if since is not None:
        query = query.gte("captured_at", since.isoformat())
    rows = query.order("captured_at").execute().data
    return [_to_history(r) for r in rows]
