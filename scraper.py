import asyncio
import re
import subprocess
import sys
import threading
from bs4 import BeautifulSoup
from urllib.parse import urlparse


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
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
    "--disable-extensions",
    "--disable-default-apps",
    "--no-first-run",
    "--disable-blink-features=AutomationControlled",
]

_BLOCKED_TYPES = {"image", "stylesheet", "font", "media", "other"}


async def _fetch_async(url: str) -> str:
    """Async Playwright fetch — runs inside asyncio.run() so it owns a clean event loop."""
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_CHROMIUM_ARGS)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
        )
        page = await context.new_page()

        async def _route_handler(route):
            if route.request.resource_type in _BLOCKED_TYPES:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", _route_handler)
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_selector("#productTitle", timeout=15_000)
        except PWTimeout:
            pass

        html = await page.content()
        await browser.close()
        return html


def _get_page_html(url: str) -> str:
    """Run the async fetch in a thread so asyncio.run() gets a guaranteed-clean event loop.

    Playwright's sync_api is broken on Python 3.14 (asyncio internals changed).
    asyncio.run() creates a fresh loop from scratch, avoiding all conflicts with
    Streamlit's own event loop.
    """
    result: dict = {}

    def _run():
        try:
            result["html"] = asyncio.run(_fetch_async(url))
        except Exception as exc:
            result["error"] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=60)

    if t.is_alive():
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
