"""AliExpress retailer adapter.

AliExpress uses hashed CSS class names with stable *prefixes* (e.g.
`price-default--current--XXXX`), so we match on the prefix via [class*=...].
It has anti-bot protection (baxia) that may occasionally serve a challenge
instead of the product; when that happens, scraping returns an error.
Stock isn't exposed reliably, so it's skipped.
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .generic import GenericAdapter, _parse_price

_TITLE_SELECTORS = ['h1[data-pl="product-title"]', ".product-title-text", "h1"]
_TITLE_CSS = 'h1[data-pl="product-title"]'
_PRICE_SELECTORS = [
    '[class*="price-default--current"]',
    '[class*="product-price-current"]',
    '[class*="--current--"]',
]
_IMAGE_SELECTORS = ['[class*="image-view"] img', 'img[class*="magnifier"]']


class AliExpressAdapter(RetailerAdapter):
    name = "aliexpress"
    wait_css = _TITLE_CSS
    settle_seconds = 3.0

    def matches(self, url: str) -> bool:
        return "aliexpress." in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop tracking query

    def _parse(self, html: str, clean_url: str) -> ProductData:
        soup = BeautifulSoup(html, "lxml")
        name = self._first_text(soup, _TITLE_SELECTORS)
        if not name:
            return ProductData(
                url=clean_url,
                error="Could not read the AliExpress product (it may have shown an "
                      "anti-bot page, or the listing was removed).",
            )
        price, currency = self._extract_price(soup)
        return ProductData(
            url=clean_url, name=name, price=price, currency=currency,
            stock=None, image_url=self._extract_image(soup),
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
            text = el.get_text(strip=True)
            price = _parse_price(text)
            if price is not None:
                currency = re.sub(r"[\d\s.,]", "", text).strip() or "TL"
                return price, currency
        data = GenericAdapter._from_jsonld(soup)
        if data.get("price") is not None:
            return data["price"], data.get("currency") or "TL"
        return None, ""

    @staticmethod
    def _extract_image(soup) -> Optional[str]:
        og = soup.find("meta", property="og:image")
        if og and og.get("content", "").startswith("http"):
            return og["content"]
        for sel in _IMAGE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                src = el.get("src") or el.get("data-src")
                if src and src.startswith("http"):
                    return src
        return None
