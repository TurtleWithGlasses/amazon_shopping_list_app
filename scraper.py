import re
import subprocess
import sys
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


def install_browser():
    """Download Playwright's Chromium if not already present (runs once on cold start)."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, check=False
    )


def _normalize_url(url: str) -> str:
    """Strip session/referral query params, keep only /dp/{ASIN}."""
    parsed = urlparse(url)
    match = re.search(r"/dp/([A-Z0-9]{10})", parsed.path, re.IGNORECASE)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/dp/{match.group(1)}"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",      # use /tmp instead of tiny /dev/shm on cloud containers
    "--disable-gpu",
    "--disable-setuid-sandbox",
    "--disable-extensions",
    "--disable-default-apps",
    "--no-first-run",
    "--disable-blink-features=AutomationControlled",
]

# Block resource types that are useless for scraping but consume significant memory.
# Images alone account for 60-70% of a typical Amazon page's payload.
_BLOCKED_TYPES = {"image", "stylesheet", "font", "media", "other"}


def _launch_and_fetch(p, url: str) -> str:
    browser = p.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        locale="tr-TR",
        timezone_id="Europe/Istanbul",
    )
    page = context.new_page()

    def _route_handler(route):
        if route.request.resource_type in _BLOCKED_TYPES:
            route.abort()
        else:
            route.continue_()

    page.route("**/*", _route_handler)

    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("#productTitle", timeout=15_000)
    except PWTimeout:
        pass

    html = page.content()
    browser.close()
    return html


def _get_page_html(url: str) -> str:
    """Run Playwright in an isolated thread to avoid asyncio conflicts with Streamlit."""
    import threading

    result: dict = {}

    def _run():
        try:
            with sync_playwright() as p:
                result["html"] = _launch_and_fetch(p, url)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=60)

    if thread.is_alive():
        raise TimeoutError("Browser timed out after 60 seconds")
    if "error" in result:
        raise result["error"]
    return result.get("html", "")


PRICE_CONTAINER_SELECTORS = [
    "#corePrice_feature_div .a-price[data-a-size='xl']",
    "#corePrice_feature_div .a-price[data-a-size='b']",
    "#corePriceDisplay_desktop_feature_div .a-price[data-a-size='xl']",
    "#corePriceDisplay_desktop_feature_div .a-price[data-a-size='b']",
    "#apex_offerDisplay_desktop .a-price[data-a-size='xl']",
    "#apex_offerDisplay_desktop .a-price[data-a-size='b']",
    "#desktop_qualifiedBuyBox .a-price[data-a-size='xl']",
    "#desktop_qualifiedBuyBox .a-price[data-a-size='b']",
    ".apex-pricetopay-value",
    ".a-price[data-a-size='xl']",
    ".a-price[data-a-size='b']",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#price_inside_buybox",
    "#kindle-price",
]

STOCK_SELECTORS = [
    "#availability .primary-availability-message",
    "#availability .a-color-price",
    "#merchantAvailability span",
    "#availability span",
    ".primary-availability-message",
]


def _extract_price_and_currency(soup) -> tuple[float | None, str]:
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
        # Fallback: legacy plain-text price element
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
        html = _get_page_html(clean_url)
    except Exception as e:
        return {"name": None, "price": None, "currency": "", "stock": None, "url": clean_url, "error": str(e)}

    soup = BeautifulSoup(html, "lxml")

    name_el = soup.select_one("#productTitle")
    name = name_el.get_text(strip=True) if name_el else None

    price, currency = _extract_price_and_currency(soup)

    stock_el = next(
        (soup.select_one(sel) for sel in STOCK_SELECTORS if soup.select_one(sel)),
        None
    )
    stock = " ".join(stock_el.get_text().split()) if stock_el else "Unknown"

    if not name:
        return {
            "name": None, "price": None, "currency": "", "stock": None,
            "url": clean_url,
            "error": "Could not parse product — page may have been blocked or shown a CAPTCHA.",
        }

    return {"name": name, "price": price, "currency": currency, "stock": stock, "url": clean_url, "error": None}
