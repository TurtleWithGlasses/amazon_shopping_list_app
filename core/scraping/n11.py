"""n11.com retailer adapter.

n11 is a JS-rendered (Vue) site; the rendered DOM is available because we fetch
with Selenium. Current price is `.newPrice ins` (`.oldPrice` is the pre-discount
price). Stock/image selectors are best-effort and refined against live pages.
"""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter
from .generic import GenericAdapter, _parse_price

_TITLE_SELECTORS = ["h1.title", ".titleArea h1", ".product-detail h1"]
_TITLE_CSS = ", ".join(_TITLE_SELECTORS)
# The visible price (.newPrice ins) is filled by a bot-gated XHR (a skeleton
# shows until then), but the value is embedded in the page's JS state as
# "priceFloat":<selling price>. The "displayPriceFloat" key (old/list price)
# does not match this pattern, so the first hit is the main product's price.
_PRICE_FLOAT_RE = re.compile(r'"priceFloat"\s*:\s*([0-9]+(?:\.[0-9]+)?)')
_PRICE_SELECTORS = [
    ".newPrice ins",
    ".priceContainer .newPrice",
    "ins.newPrice",
    ".price-wrapper ins",
    ".newPrice",
]
_IMAGE_SELECTORS = [
    ".imageSlider .swiper-slide-active img",
    ".imageSlider img.swiper-image",
    ".productHead .imageSlider img",
    ".left-area img",
]


class N11Adapter(RetailerAdapter):
    name = "n11"
    wait_css = _TITLE_CSS

    def matches(self, url: str) -> bool:
        return "n11.com" in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"  # drop query/fragment

    def _parse(self, html: str, clean_url: str) -> ProductData:
        soup = BeautifulSoup(html, "lxml")
        name = self._first_text(soup, _TITLE_SELECTORS)
        if not name:
            return ProductData(
                url=clean_url,
                error="Could not find the product on n11 (layout may have changed "
                      "or the listing was removed).",
            )
        price, currency = self._extract_price(html, soup)
        # n11 product pages don't expose a reliable stock status, so we skip it.
        return ProductData(
            url=clean_url, name=name, price=price, currency=currency,
            stock=None, image_url=self._extract_image(soup),
        )

    @staticmethod
    def _first_text(soup, selectors) -> Optional[str]:
        for sel in selectors:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                return " ".join(el.get_text().split())
        return None

    @staticmethod
    def _extract_price(html, soup) -> Tuple[Optional[float], str]:
        # Primary: the selling price embedded in the page's JS state.
        match = _PRICE_FLOAT_RE.search(html)
        if match:
            return float(match.group(1)), "TL"
        # Fallback: rendered DOM (works if the price XHR completed).
        for sel in _PRICE_SELECTORS:
            el = soup.select_one(sel)
            if not el:
                continue
            text = el.get_text(strip=True)
            price = _parse_price(text)
            if price is not None:
                currency = re.sub(r"[\d\s.,]", "", text).strip() or "TL"
                return price, currency
        # Last resort: structured data (JSON-LD / Open Graph).
        data = GenericAdapter._from_jsonld(soup)
        if data.get("price") is not None:
            return data["price"], data.get("currency") or "TL"
        og = GenericAdapter._from_opengraph(soup)
        if og.get("price") is not None:
            return og["price"], og.get("currency") or "TL"
        return None, ""

    @staticmethod
    def _extract_image(soup) -> Optional[str]:
        for sel in _IMAGE_SELECTORS:
            el = soup.select_one(sel)
            if el:
                src = el.get("src") or el.get("data-src") or el.get("data-original")
                if src and src.startswith("http"):
                    return src
        og = soup.find("meta", property="og:image")
        return og["content"] if og and og.get("content") else None
