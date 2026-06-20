"""Generic retailer adapter.

Handles any non-Amazon site by reading standardized structured data:
schema.org JSON-LD `Product` first, then Open Graph / product meta tags. This
covers many e-commerce sites (which embed this data for SEO) without bespoke
per-site selectors. Sites that expose neither return a clear error.
"""
import json
import re
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .browser import get_page_html


def _parse_price(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d.,]", "", str(value))
    if not s:
        return None
    if "," in s and "." in s:
        # the right-most separator is the decimal point
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".") if re.search(r",\d{2}$", s) else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _first_image(image) -> Optional[str]:
    if isinstance(image, str):
        return image
    if isinstance(image, list) and image:
        first = image[0]
        return first if isinstance(first, str) else (first.get("url") if isinstance(first, dict) else None)
    if isinstance(image, dict):
        return image.get("url")
    return None


def _availability_to_stock(availability) -> Optional[str]:
    if not availability:
        return None
    s = str(availability).lower()
    if "outofstock" in s or "soldout" in s or "out of stock" in s or "discontinued" in s:
        return "Out of stock"
    if "limited" in s:
        return "Limited stock"
    if "instock" in s or "in stock" in s or "onlineonly" in s or "presale" in s:
        return "In stock"
    return None


def _find_product_node(obj):
    if isinstance(obj, dict):
        types = obj.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(isinstance(t, str) and t.lower() == "product" for t in types):
            return obj
        if "@graph" in obj:
            found = _find_product_node(obj["@graph"])
            if found:
                return found
        for value in obj.values():
            found = _find_product_node(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_product_node(item)
            if found:
                return found
    return None


class GenericAdapter(RetailerAdapter):
    name = "generic"

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop query/fragment

    def scrape(self, url: str) -> ProductData:
        clean_url = self.normalize_url(url)
        try:
            html = get_page_html(clean_url)
        except Exception as exc:
            return ProductData(url=clean_url, error=str(exc))

        soup = BeautifulSoup(html, "lxml")
        data = self._from_jsonld(soup)
        og = self._from_opengraph(soup)

        name = data.get("name") or og.get("name")
        price = data.get("price") if data.get("price") is not None else og.get("price")
        currency = data.get("currency") or og.get("currency") or ""
        stock = data.get("stock") or og.get("stock") or "Unknown"
        image = data.get("image") or og.get("image")

        if not name and price is None:
            return ProductData(
                url=clean_url,
                error="Could not read product data from this page "
                      "(no schema.org or Open Graph product data found).",
            )
        return ProductData(
            url=clean_url, name=name, price=price, currency=currency,
            stock=stock, image_url=image,
        )

    @staticmethod
    def _from_jsonld(soup) -> dict:
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                node = _find_product_node(json.loads(raw))
            except (ValueError, TypeError):
                continue
            if not node:
                continue
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            return {
                "name": node.get("name"),
                "image": _first_image(node.get("image")),
                "price": _parse_price(offers.get("price") or offers.get("lowPrice")),
                "currency": offers.get("priceCurrency") or "",
                "stock": _availability_to_stock(offers.get("availability")),
            }
        return {}

    @staticmethod
    def _from_opengraph(soup) -> dict:
        def meta(*props):
            for prop in props:
                el = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
                if el and el.get("content"):
                    return el["content"]
            return None

        return {
            "name": meta("og:title"),
            "image": meta("og:image"),
            "price": _parse_price(meta("product:price:amount", "og:price:amount")),
            "currency": meta("product:price:currency", "og:price:currency"),
            "stock": _availability_to_stock(meta("product:availability", "og:availability")),
        }
