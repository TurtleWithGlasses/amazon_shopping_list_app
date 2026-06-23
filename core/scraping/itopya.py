"""itopya.com retailer adapter.

İtopya uses clean (non-hashed) class names. Note: its JSON-LD price differs from
the displayed price, so we read the visible DOM price (`.product-details__sidebar_newprice`)
and do NOT fall back to JSON-LD for price.
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .generic import _parse_price

_TITLE_SELECTORS = ["h1.product-details-title", ".product-details__content h1", "h1"]
_TITLE_CSS = "h1.product-details-title"
_PRICE_SELECTORS = [
    ".product-details__sidebar_newprice",
    ".product-details__sidebar_price strong",
    '[class*="newprice"]',
]
_OUT_PHRASES = ("tükendi", "tukendi", "stokta yok", "stok yok", "temin edilemiyor")


class ItopyaAdapter(RetailerAdapter):
    name = "itopya"
    wait_css = _TITLE_CSS
    # JS-rendered title: wait for non-empty text, not just element presence.
    wait_text_css = _TITLE_CSS
    settle_seconds = 2.5

    def matches(self, url: str) -> bool:
        return "itopya.com" in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop tracking query

    def _parse(self, html: str, clean_url: str) -> ProductData:
        soup = BeautifulSoup(html, "lxml")
        name = self._first_text(soup, _TITLE_SELECTORS)
        if not name:
            return ProductData(
                url=clean_url,
                error="Could not find the product on İtopya (layout may have "
                      "changed or the listing was removed).",
            )
        price, currency = self._extract_price(soup)
        return ProductData(
            url=clean_url, name=name, price=price, currency=currency,
            stock=self._extract_stock(soup), image_url=self._extract_image(soup),
        )

    @staticmethod
    def _first_text(soup, selectors) -> Optional[str]:
        for sel in selectors:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                return " ".join(el.get_text(" ").split())
        return None

    @staticmethod
    def _extract_price(soup) -> Tuple[Optional[float], str]:
        for sel in _PRICE_SELECTORS:
            el = soup.select_one(sel)
            if not el:
                continue
            text = el.get_text(" ", strip=True)
            price = _parse_price(text)
            if price is not None:
                currency = re.sub(r"[\d\s.,]", "", text).strip() or "TL"
                return price, currency
        return None, ""  # do NOT use JSON-LD here — its price is stale/different

    @staticmethod
    def _extract_stock(soup) -> str:
        text = soup.get_text(" ", strip=True).lower()
        if any(p in text for p in _OUT_PHRASES):
            return "Out of stock"
        return "In stock"

    @staticmethod
    def _extract_image(soup) -> Optional[str]:
        img = soup.select_one('img[data-id="imgMain"]')
        if img and img.get("src", "").startswith("http"):
            return img["src"]
        og = soup.find("meta", property="og:image")
        return og["content"] if og and og.get("content", "").startswith("http") else None
