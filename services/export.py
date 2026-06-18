"""Export the tracked list + price history to CSV / Excel for a timescale."""
from typing import Optional

import pandas as pd

from core import repository as repo
from .timescales import since_for

_COLUMNS = ["product", "retailer", "url", "captured_at", "price", "currency", "stock"]


def build_export_dataframe(since=None) -> pd.DataFrame:
    """One row per (product, history point) within the timescale.

    Products with no history in range still contribute their current snapshot,
    so an export is never silently empty.
    """
    records = []
    for product in repo.list_products():
        history = repo.get_price_history(product.id, since=since)
        if history:
            for point in history:
                records.append({
                    "product": product.name,
                    "retailer": product.retailer,
                    "url": product.url,
                    "captured_at": point.captured_at,
                    "price": point.price,
                    "currency": product.currency,
                    "stock": point.stock,
                })
        else:
            records.append({
                "product": product.name,
                "retailer": product.retailer,
                "url": product.url,
                "captured_at": product.last_checked,
                "price": product.last_price,
                "currency": product.currency,
                "stock": product.last_stock,
            })
    return pd.DataFrame(records, columns=_COLUMNS)


def export_to_file(path: str, timescale_label: Optional[str] = None) -> int:
    """Write the export to `path` (.xlsx → Excel, otherwise CSV). Returns row count."""
    since = since_for(timescale_label) if timescale_label else None
    df = build_export_dataframe(since)
    if path.lower().endswith((".xlsx", ".xls")):
        df.to_excel(path, index=False)
    else:
        # utf-8-sig so Excel opens Turkish characters correctly from CSV
        df.to_csv(path, index=False, encoding="utf-8-sig")
    return len(df)
