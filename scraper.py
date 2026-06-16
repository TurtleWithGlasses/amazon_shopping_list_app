import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
    _CURL_AVAILABLE = True
except ImportError:
    _CURL_AVAILABLE = False

# Fallback headers used only when curl_cffi is unavailable
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "DNT": "1",
}


def _fetch(url: str):
    """Fetch URL impersonating Chrome TLS fingerprint to bypass bot detection."""
    if _CURL_AVAILABLE:
        return curl_requests.get(url, impersonate="chrome120", timeout=15)
    return requests.get(url, headers=_HEADERS, timeout=12)


def _normalize_url(url: str) -> str:
    """Strip query params and build a clean /dp/{ASIN} URL.

    Wishlist/referral params (coliid, colid, ref_=...) require an authenticated
    Amazon session — without one, Amazon returns 500. The ASIN in the path is
    sufficient to identify the product.
    """
    parsed = urlparse(url)
    match = re.search(r"/dp/([A-Z0-9]{10})", parsed.path, re.IGNORECASE)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/dp/{match.group(1)}"
    # No ASIN found — drop query string but keep path as-is
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

PRICE_CONTAINER_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price",
    ".apex-pricetopay-value",
    ".a-price[data-a-size='xl']",
    ".a-price[data-a-size='b']",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
    "#kindle-price",
    ".a-price",
]


def _extract_price_and_currency(soup) -> tuple[float | None, str]:
    """
    Parse price from structured span components (a-price-whole / a-price-fraction /
    a-price-symbol). Stripping all non-digits from the whole part makes this
    locale-agnostic: "10.949" (TR) and "10,949" (US) both become "10949".
    """
    for sel in PRICE_CONTAINER_SELECTORS:
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

        # Fallback: plain text element (legacy selectors like #priceblock_ourprice)
        text = container.get_text(strip=True)
        if text:
            currency = re.sub(r"[\d\s.,]", "", text).strip()
            digits = re.sub(r"[^\d.]", "", text.replace(",", ""))
            match = re.search(r"\d+\.?\d*", digits)
            if match:
                return float(match.group()), currency

    return None, ""


def scrape_product(url: str) -> dict:
    clean_url = _normalize_url(url)
    try:
        resp = _fetch(clean_url)
        resp.raise_for_status()
    except Exception as e:
        return {"name": None, "price": None, "currency": "", "stock": None, "url": clean_url, "error": str(e)}

    soup = BeautifulSoup(resp.text, "lxml")

    name_el = soup.select_one("#productTitle")
    name = name_el.get_text(strip=True) if name_el else None

    price, currency = _extract_price_and_currency(soup)

    stock_el = soup.select_one("#availability span")
    stock = stock_el.get_text(strip=True) if stock_el else "Unknown"

    if not name:
        return {"name": None, "price": None, "currency": "", "stock": None, "url": clean_url, "error": "Could not parse product — Amazon may have blocked the request."}

    return {"name": name, "price": price, "currency": currency, "stock": stock, "url": clean_url, "error": None}
