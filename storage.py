import json
import os
from datetime import datetime

STORAGE_FILE = "products.json"


def load_products() -> list[dict]:
    if not os.path.exists(STORAGE_FILE):
        return []
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_products(products: list[dict]) -> None:
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)


def add_product(url: str, name: str, price: float | None, currency: str, stock: str) -> None:
    products = load_products()
    products.append({
        "id": datetime.now().isoformat(),
        "url": url,
        "name": name,
        "price": price,
        "currency": currency,
        "stock": stock,
        "last_checked": datetime.now().isoformat(),
        "price_changed": False,
        "stock_changed": False,
        "prev_price": None,
        "prev_stock": None,
    })
    save_products(products)


def delete_product(product_id: str) -> None:
    products = [p for p in load_products() if p["id"] != product_id]
    save_products(products)


def update_product(product_id: str, name: str, url: str) -> None:
    products = load_products()
    for p in products:
        if p["id"] == product_id:
            p["name"] = name
            p["url"] = url
    save_products(products)


def refresh_all_products(scrape_fn) -> list[str]:
    """Scrape every tracked product and persist changes. Returns names of changed products."""
    products = load_products()
    changed_names = []

    for p in products:
        result = scrape_fn(p["url"])
        if result["error"]:
            continue

        new_price = result["price"]
        new_stock = result["stock"]

        price_changed = new_price is not None and new_price != p["price"]
        stock_changed = new_stock != p["stock"] and new_stock != "Unknown"

        p["prev_price"] = p["price"]
        p["prev_stock"] = p["stock"]
        p["price"] = new_price
        p["currency"] = result.get("currency", p.get("currency", ""))
        p["stock"] = new_stock
        p["price_changed"] = price_changed
        p["stock_changed"] = stock_changed
        p["last_checked"] = datetime.now().isoformat()

        if price_changed or stock_changed:
            changed_names.append(p["name"])

    save_products(products)
    return changed_names
