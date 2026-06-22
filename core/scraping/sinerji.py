"""sinerji.gen.tr retailer adapter (clean class names)."""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .generic import _parse_price

_TITLE_SELECTORS = [".pageTitle h1", ".productDetail .pageTitle h1", "h1"]
_TITLE_CSS = ".pageTitle h1"
_PRICE_SELECTORS = [".priceWrapper .price", ".defaultPrice", ".price"]
_OUT_PHRASES = ("tükendi", "tukendi", "stokta yok", "stok yok", "temin edilemiyor")


class SinerjiAdapter(RetailerAdapter):
    name = "sinerji"
    wait_css = _TITLE_CSS

    def matches(self, url: str) -> bool:
        return "sinerji.gen.tr" in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop tracking query

    def _parse(self, html: str, clean_url: str) -> ProductData:
        soup = BeautifulSoup(html, "lxml")
        name = self._first_text(soup, _TITLE_SELECTORS)
        if not name:
            return ProductData(
                url=clean_url,
                error="Could not find the product on Sinerji (layout may have "
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
    def _extract_image(soup) -> Optional[str]:
        link = soup.select_one(".productPhotoCarouselPhotoLink[data-img]")
        if link and link.get("data-img", "").startswith("http"):
            return link["data-img"]
        img = soup.select_one("img.productPhotoCarouselPhoto") or soup.select_one(".productPhotoCarousel img")
        if img and img.get("src", "").startswith("http"):
            return img["src"]
        og = soup.find("meta", property="og:image")
        return og["content"] if og and og.get("content", "").startswith("http") else None
