"""hepsiburada.com retailer adapter.

Hepsiburada's CSS class names are hashed and change per build, so we rely on the
stable `data-test-id` hooks (title / default-price) and, as a fallback, the
price embedded in the page's `data-hbus` JSON (`"price":"3336.9"`).
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .browser import get_page_html
from .generic import GenericAdapter, _parse_price

_TITLE_SELECTORS = ['h1[data-test-id="title"]', '[data-test-id="title-area"] h1', '[data-test-id="title"]']
_TITLE_CSS = ", ".join(_TITLE_SELECTORS)
_PRICE_SELECTORS = ['[data-test-id="default-price"]', '[data-test-id="price"]']
_IMAGE_SELECTORS = ['img[data-test-id="product-image"]', "picture img", ".product-detail img"]
# data-hbus JSON carries "price":"3336.9" as a string.
_EMBEDDED_PRICE_RE = re.compile(r'"price"\s*:\s*"([0-9]+(?:\.[0-9]+)?)"')
_OUT_PHRASES = ("tükendi", "tukendi", "satıcı bulunmuyor", "satici bulunmuyor",
                "geçici olarak temin", "gecici olarak temin")


class HepsiburadaAdapter(RetailerAdapter):
    name = "hepsiburada"

    def matches(self, url: str) -> bool:
        return "hepsiburada.com" in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop query/fragment

    def scrape(self, url: str) -> ProductData:
        clean_url = self.normalize_url(url)
        try:
            html = get_page_html(clean_url, wait_css=_TITLE_CSS, settle_seconds=2.0)
        except Exception as exc:
            return ProductData(url=clean_url, error=str(exc))

        soup = BeautifulSoup(html, "lxml")
        name = self._first_text(soup, _TITLE_SELECTORS)
        if not name:
            return ProductData(
                url=clean_url,
                error="Could not find the product on Hepsiburada (layout may have "
                      "changed or the listing was removed).",
            )
        price, currency = self._extract_price(html, soup)
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
    def _extract_price(html, soup) -> Tuple[Optional[float], str]:
        for sel in _PRICE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                price = _parse_price(text)
                if price is not None:
                    currency = re.sub(r"[\d\s.,]", "", text).strip() or "TL"
                    return price, currency
        # Fallback: price embedded in the data-hbus JSON.
        match = _EMBEDDED_PRICE_RE.search(html)
        if match:
            return float(match.group(1)), "TL"
        # Last resort: structured data.
        data = GenericAdapter._from_jsonld(soup)
        if data.get("price") is not None:
            return data["price"], data.get("currency") or "TL"
        og = GenericAdapter._from_opengraph(soup)
        if og.get("price") is not None:
            return og["price"], og.get("currency") or "TL"
        return None, ""

    @staticmethod
    def _extract_stock(soup) -> Optional[str]:
        text = (soup.select_one("body") or soup).get_text(" ", strip=True).lower()
        if any(p in text for p in _OUT_PHRASES):
            return "Out of stock"
        if "sepete ekle" in text:
            return "In stock"
        return None

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
