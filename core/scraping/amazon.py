"""Amazon retailer adapter (amazon.com.tr and other Amazon domains)."""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import ProductData, RetailerAdapter

_TITLE_SELECTORS = ["#productTitle", "#title", "h1.a-size-large span", "#btAsinTitle"]
_TITLE_CSS = ", ".join(_TITLE_SELECTORS)

# Ordered by reliability: the "price to pay" widget is the actual checkout price.
_PRICE_CONTAINER_SELECTORS = [
    ".apex-pricetopay-value",
    "#corePrice_feature_div .a-price[data-a-size='xl']",
    "#corePrice_feature_div .a-price[data-a-size='b']",
    "#corePrice_feature_div .a-price[data-a-size='l']",
    "#corePriceDisplay_desktop_feature_div .a-price[data-a-size='xl']",
    "#corePriceDisplay_desktop_feature_div .a-price[data-a-size='b']",
    "#corePriceDisplay_desktop_feature_div .a-price[data-a-size='l']",
    "#apex_offerDisplay_desktop .a-price[data-a-size='xl']",
    "#apex_offerDisplay_desktop .a-price[data-a-size='b']",
    "#apex_offerDisplay_desktop .a-price[data-a-size='l']",
    "#desktop_qualifiedBuyBox .a-price[data-a-size='xl']",
    "#desktop_qualifiedBuyBox .a-price[data-a-size='b']",
    "#desktop_qualifiedBuyBox .a-price[data-a-size='l']",
    ".a-price[data-a-size='xl']",
    ".a-price[data-a-size='b']",
    ".a-price[data-a-size='l']",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
    "#kindle-price",
]

_STOCK_SELECTORS = [
    "#availability .primary-availability-message",
    "#availability .a-color-price",
    "#merchantAvailability span",
    "#availability span",
    ".primary-availability-message",
]

_IMAGE_SELECTORS = [
    "#landingImage",
    "#imgTagWrapperId img",
    "#main-image-container img",
    "#imgBlkFront",
    "#ebooksImgBlkFront",
    ".a-dynamic-image",
]


class AmazonAdapter(RetailerAdapter):
    name = "amazon"
    wait_css = _TITLE_CSS
    # Amazon occasionally renders a partial page; re-fetch once after a pause.
    selenium_attempts = 2
    selenium_retry_sleep = 4.0

    def matches(self, url: str) -> bool:
        return "amazon." in urlparse(url).netloc.lower()

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        match = re.search(
            r"/(?:dp|gp/product)/([A-Z0-9]{10})", parsed.path, re.IGNORECASE
        )
        if match:
            return f"{parsed.scheme}://{parsed.netloc}/dp/{match.group(1)}"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def _parse(self, html: str, clean_url: str) -> ProductData:
        soup = BeautifulSoup(html, "lxml")
        name = self._extract_name(soup)
        if not name:
            return ProductData(url=clean_url, error=self._classify_failure(soup))

        price, currency = self._extract_price_and_currency(soup)
        stock = self._extract_stock(soup)
        image_url = self._extract_image(soup)
        return ProductData(
            url=clean_url, name=name, price=price, currency=currency,
            stock=stock, image_url=image_url,
        )

    # --- parsing helpers ---------------------------------------------------

    @staticmethod
    def _extract_name(soup) -> Optional[str]:
        element = next(
            (soup.select_one(sel) for sel in _TITLE_SELECTORS if soup.select_one(sel)),
            None,
        )
        return element.get_text(strip=True) if element else None

    @staticmethod
    def _extract_price_and_currency(soup) -> Tuple[Optional[float], str]:
        for sel in _PRICE_CONTAINER_SELECTORS:
            container = soup.select_one(sel)
            if not container:
                continue
            whole_el = container.select_one(".a-price-whole")
            fraction_el = container.select_one(".a-price-fraction")
            symbol_el = container.select_one(".a-price-symbol")
            if whole_el:
                whole = re.sub(r"[^\d]", "", whole_el.get_text())
                fraction = re.sub(r"[^\d]", "", fraction_el.get_text()) if fraction_el else "00"
                currency = symbol_el.get_text(strip=True) if symbol_el else ""
                if whole:
                    return float(f"{whole}.{fraction}"), currency
            text = container.get_text(strip=True)
            if text:
                currency = re.sub(r"[\d\s.,]", "", text).strip()
                digits = re.sub(r"[^\d.]", "", text.replace(",", ""))
                match = re.search(r"\d+\.?\d*", digits)
                if match:
                    return float(match.group()), currency
        return None, ""

    @staticmethod
    def _extract_stock(soup) -> str:
        element = next(
            (soup.select_one(sel) for sel in _STOCK_SELECTORS if soup.select_one(sel)),
            None,
        )
        return " ".join(element.get_text().split()) if element else "Unknown"

    @staticmethod
    def _extract_image(soup) -> Optional[str]:
        for sel in _IMAGE_SELECTORS:
            element = soup.select_one(sel)
            if not element:
                continue
            for attr in ("data-old-hires", "src"):
                value = element.get(attr)
                if value and value.startswith("http"):
                    return value
            dynamic = element.get("data-a-dynamic-image")
            if dynamic:
                try:
                    import json
                    urls = json.loads(dynamic)
                    if urls:
                        return next(iter(urls))
                except Exception:
                    pass
        return None

    @staticmethod
    def _classify_failure(soup) -> str:
        if soup is None:
            return "Could not load the product page."
        text = soup.get_text(" ", strip=True).lower()
        if "captcha" in text or "robot" in text or "automated" in text:
            return "Amazon showed a CAPTCHA / robot-check page. Try again in a few seconds."
        if "sign in" in text and "password" in text:
            return "Amazon redirected to a sign-in page — this product may require a logged-in session."
        if "unavailable" in text or "page not found" in text or "doesn't exist" in text:
            return "Product page not found — the URL may be incorrect or the listing removed."
        return "Could not find product title. Amazon may have served a different page layout."
