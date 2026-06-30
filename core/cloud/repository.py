"""Cloud (Supabase Postgres) repository.

Mirrors core/repository.py's API so it can be swapped in via core/datastore.py
after login. Row-level security scopes every query to the logged-in user; we
also set user_id explicitly on insert to satisfy the RLS check constraint.

Returns lightweight dataclasses with the same attribute names the UI expects.
"""
import functools
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from .auth import current_user_id
from .client import get_client


def _resilient(func):
    """Retry a Supabase call on transient network errors.

    Supabase's HTTP/2 keep-alive connections can be dropped while idle
    ("Server disconnected"); retrying issues a fresh request/connection.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(3):
            try:
                return func(*args, **kwargs)
            except httpx.TransportError as exc:
                last_error = exc
                time.sleep(0.4 * (attempt + 1))
        raise last_error
    return wrapper


@dataclass
class CloudProduct:
    id: int
    url: str
    retailer: str
    name: Optional[str]
    currency: str
    image_url: Optional[str]
    last_price: Optional[float]
    last_stock: Optional[str]
    prev_price: Optional[float]
    prev_stock: Optional[str]
    price_changed: bool
    stock_changed: bool
    position: int
    created_at: Optional[datetime]
    last_checked: Optional[datetime]
    target_price: Optional[float] = None


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
        image_url=row.get("image_url"),
        last_price=row.get("last_price"),
        last_stock=row.get("last_stock"),
        prev_price=row.get("prev_price"),
        prev_stock=row.get("prev_stock"),
        price_changed=bool(row.get("price_changed")),
        stock_changed=bool(row.get("stock_changed")),
        position=row.get("position") or 0,
        created_at=_parse_dt(row.get("created_at")),
        last_checked=_parse_dt(row.get("last_checked")),
        target_price=row.get("target_price"),
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


@_resilient
def add_product(url, name=None, price=None, currency="", stock=None,
                retailer=None, user_id=None, image_url=None) -> CloudProduct:
    client = get_client()
    payload = {
        "user_id": user_id or current_user_id(),
        "url": url,
        "retailer": retailer or _retailer_from_url(url),
        "name": name,
        "currency": currency,
        "image_url": image_url,
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


@_resilient
def list_products(user_id=None) -> List[CloudProduct]:
    # RLS already restricts to the current user.
    rows = (
        get_client().table("products").select("*")
        .order("position").order("created_at").execute().data
    )
    return [_to_product(r) for r in rows]


@_resilient
def reorder_products(ordered_ids: List[int]) -> None:
    client = get_client()
    for index, product_id in enumerate(ordered_ids):
        client.table("products").update({"position": index}).eq("id", product_id).execute()


@_resilient
def get_product(product_id) -> Optional[CloudProduct]:
    rows = get_client().table("products").select("*").eq("id", product_id).limit(1).execute().data
    return _to_product(rows[0]) if rows else None


_UNSET = object()  # sentinel: "argument not provided" (vs. None = clear the value)


@_resilient
def update_product(product_id, name=None, url=None, target_price=_UNSET) -> Optional[CloudProduct]:
    updates = {}
    if name is not None:
        updates["name"] = name
    if url is not None:
        updates["url"] = url
        updates["retailer"] = _retailer_from_url(url)
    if target_price is not _UNSET:
        updates["target_price"] = target_price  # float to set, None to clear
    if not updates:
        return get_product(product_id)
    rows = get_client().table("products").update(updates).eq("id", product_id).execute().data
    return _to_product(rows[0]) if rows else None


@_resilient
def delete_product(product_id) -> bool:
    rows = get_client().table("products").delete().eq("id", product_id).execute().data
    return bool(rows)


@_resilient
def apply_scrape_result(product_id, name=None, price=None, currency=None,
                        stock=None, image_url=None) -> Optional[CloudProduct]:
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
    if image_url:
        updates["image_url"] = image_url

    updated = client.table("products").update(updates).eq("id", product_id).execute().data
    return _to_product(updated[0]) if updated else None


@_resilient
def record_price_snapshot(product_id, price=None, stock=None) -> Optional[CloudHistory]:
    rows = get_client().table("price_history").insert(
        {"product_id": product_id, "price": price, "stock": stock}
    ).execute().data
    return _to_history(rows[0]) if rows else None


@_resilient
def get_price_history(product_id, since=None) -> List[CloudHistory]:
    query = get_client().table("price_history").select("*").eq("product_id", product_id)
    if since is not None:
        query = query.gte("captured_at", since.isoformat())
    rows = query.order("captured_at").execute().data
    return [_to_history(r) for r in rows]


@_resilient
def recent_history(since) -> dict:
    """All price points since `since`, grouped by product id (RLS scopes to the
    user). Used to compute price trends (Phase 37). Paginated, because Supabase
    caps a single response at 1000 rows — a week of snapshots easily exceeds it,
    which would otherwise leave most products with too few points."""
    client = get_client()
    result: dict = {}
    size, start = 1000, 0
    while True:
        rows = (
            client.table("price_history").select("product_id,price,captured_at")
            .gte("captured_at", since.isoformat())
            .order("captured_at")
            .range(start, start + size - 1)
            .execute().data
        )
        for r in rows:
            result.setdefault(r["product_id"], []).append(
                (_parse_dt(r.get("captured_at")), r.get("price"))
            )
        if len(rows) < size:
            break
        start += size
    return result


# --- groups (Phase 34) ----------------------------------------------------

@dataclass
class CloudGroup:
    id: int
    name: str
    member_count: int = 0


@_resilient
def create_group(name, user_id=None) -> CloudGroup:
    row = get_client().table("groups").insert(
        {"user_id": user_id or current_user_id(), "name": name}
    ).execute().data[0]
    return CloudGroup(id=row["id"], name=row["name"], member_count=0)


@_resilient
def list_groups(user_id=None) -> List[CloudGroup]:
    client = get_client()
    rows = client.table("groups").select("*").order("created_at").execute().data
    groups = []
    for r in rows:
        count = client.table("group_members").select("id", count="exact").eq(
            "group_id", r["id"]
        ).execute().count or 0
        groups.append(CloudGroup(id=r["id"], name=r["name"], member_count=count))
    return groups


@_resilient
def rename_group(group_id, name) -> Optional[CloudGroup]:
    rows = get_client().table("groups").update({"name": name}).eq("id", group_id).execute().data
    return CloudGroup(id=rows[0]["id"], name=rows[0]["name"]) if rows else None


@_resilient
def delete_group(group_id) -> bool:
    rows = get_client().table("groups").delete().eq("id", group_id).execute().data
    return bool(rows)


@_resilient
def add_to_group(group_id, product_id) -> bool:
    client = get_client()
    existing = client.table("group_members").select("id").eq(
        "group_id", group_id
    ).eq("product_id", product_id).execute().data
    if existing:
        return False
    client.table("group_members").insert(
        {"group_id": group_id, "product_id": product_id}
    ).execute()
    return True


@_resilient
def remove_from_group(group_id, product_id) -> bool:
    rows = get_client().table("group_members").delete().eq(
        "group_id", group_id
    ).eq("product_id", product_id).execute().data
    return bool(rows)


@_resilient
def group_members(group_id) -> List[CloudProduct]:
    client = get_client()
    member_rows = client.table("group_members").select("product_id").eq(
        "group_id", group_id
    ).execute().data
    ids = [m["product_id"] for m in member_rows]
    if not ids:
        return []
    rows = client.table("products").select("*").in_("id", ids).order("position").execute().data
    return [_to_product(r) for r in rows]


@_resilient
def groups_for_product(product_id) -> List[CloudGroup]:
    client = get_client()
    member_rows = client.table("group_members").select("group_id").eq(
        "product_id", product_id
    ).execute().data
    ids = [m["group_id"] for m in member_rows]
    if not ids:
        return []
    rows = client.table("groups").select("*").in_("id", ids).order("created_at").execute().data
    return [CloudGroup(id=r["id"], name=r["name"]) for r in rows]


# --- shopping cart (Phase 38) ---------------------------------------------

@_resilient
def add_to_cart(product_id, quantity=1, user_id=None) -> bool:
    client = get_client()
    existing = client.table("cart_items").select("id").eq("product_id", product_id).execute().data
    if existing:
        return False
    client.table("cart_items").insert(
        {"user_id": user_id or current_user_id(),
         "product_id": product_id, "quantity": max(1, quantity)}
    ).execute()
    return True


@_resilient
def set_cart_quantity(product_id, quantity) -> bool:
    client = get_client()
    if quantity <= 0:
        rows = client.table("cart_items").delete().eq("product_id", product_id).execute().data
        return bool(rows)
    rows = client.table("cart_items").update(
        {"quantity": quantity}
    ).eq("product_id", product_id).execute().data
    return bool(rows)


@_resilient
def remove_from_cart(product_id) -> bool:
    rows = get_client().table("cart_items").delete().eq("product_id", product_id).execute().data
    return bool(rows)


@_resilient
def clear_cart() -> None:
    client = get_client()
    ids = [r["product_id"] for r in client.table("cart_items").select("product_id").execute().data]
    if ids:
        client.table("cart_items").delete().in_("product_id", ids).execute()


@_resilient
def cart_products() -> List[CloudProduct]:
    client = get_client()
    rows = client.table("cart_items").select("product_id,quantity").execute().data
    qty = {r["product_id"]: r["quantity"] for r in rows}
    if not qty:
        return []
    prows = client.table("products").select("*").in_("id", list(qty)).order("position").execute().data
    products = []
    for r in prows:
        product = _to_product(r)
        product.quantity = qty.get(r["id"], 1)
        products.append(product)
    return products


@_resilient
def cart_product_ids() -> set:
    rows = get_client().table("cart_items").select("product_id").execute().data
    return {r["product_id"] for r in rows}


@_resilient
def cart_count() -> int:
    return get_client().table("cart_items").select("id", count="exact").execute().count or 0
