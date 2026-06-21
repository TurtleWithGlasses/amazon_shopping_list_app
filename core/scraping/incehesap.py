"""incehesap.com retailer adapter.

Uses microdata hooks (`itemprop`) that are stable across the Tailwind utility
classes: `h1[itemprop=name]`, `[itemprop=price]` (machine-readable `content`),
and `img[itemprop=image]` (relative URL, made absolute).
"""
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .browser import get_page_html
from .generic import _parse_price

_TITLE_SELECTORS = ['h1[itemprop="name"]', "h1"]
_TITLE_CSS = 'h1[itemprop="name"]'
# Alpine.js renders the pricing block after the title — wait for the price text.
_PRICE_WAIT_CSS = ".price"
_OUT_PHRASES = ("tükendi", "tukendi", "stokta yok", "stok yok", "temin edilemiyor")


class IncehesapAdapter(RetailerAdapter):
    name = "incehesap"

    def matches(self, url: str) -> bool:
        return "incehesap.com" in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop tracking query

    def scrape(self, url: str) -> ProductData:
        clean_url = self.normalize_url(url)
        try:
            html = get_page_html(
                clean_url, wait_css=_TITLE_CSS,
                wait_text_css=_PRICE_WAIT_CSS, settle_seconds=2.0,
            )
        except Exception as exc:
            return ProductData(url=clean_url, error=str(exc))

        soup = BeautifulSoup(html, "lxml")
        name = self._first_text(soup, _TITLE_SELECTORS)
        if not name:
            return ProductData(
                url=clean_url,
                error="Could not find the product on İncehesap (layout may have "
                      "changed or the listing was removed).",
            )
        price, currency = self._extract_price(soup)
        return ProductData(
            url=clean_url, name=name, price=price, currency=currency,
            stock=self._extract_stock(soup),
            image_url=self._extract_image(soup, clean_url),
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
        # Primary: machine-readable microdata price.
        el = soup.select_one("[itemprop=price]")
        if el:
            price = _parse_price(el.get("content") or el.get_text(strip=True))
            if price is not None:
                return price, "TL"
        # Fallback: the visible price (scoped to the pricing block).
        for sel in [".order-4 .price", ".price"]:
            el = soup.select_one(sel)
            if el:
                price = _parse_price(el.get_text(" ", strip=True))
                if price is not None:
                    return price, "TL"
        return None, ""

    @staticmethod
    def _extract_stock(soup) -> str:
        text = soup.get_text(" ", strip=True).lower()
        if any(p in text for p in _OUT_PHRASES):
            return "Out of stock"
        return "In stock"

    @staticmethod
    def _extract_image(soup, base) -> Optional[str]:
        img = soup.select_one('img[itemprop="image"]')
        if img and img.get("src"):
            return urljoin(base, img["src"])  # src is relative on this site
        og = soup.find("meta", property="og:image")
        return og["content"] if og and og.get("content", "").startswith("http") else None
