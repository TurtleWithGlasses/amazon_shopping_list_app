import re
import sys
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    # Match /dp/ASIN or /gp/product/ASIN — both are valid Amazon product URL forms
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", parsed.path, re.IGNORECASE)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/dp/{match.group(1)}"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


_TITLE_SELECTORS = ["#productTitle", "#title", "h1.a-size-large span", "#btAsinTitle"]
# CSS selector that matches any known title element — used by WebDriverWait
_TITLE_CSS = ", ".join(_TITLE_SELECTORS)


def _build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=tr")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    if sys.platform.startswith("linux"):
        # Streamlit Cloud / Linux: use system Chromium installed via packages.txt
        options.binary_location = "/usr/bin/chromium"
        return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    # Windows / macOS: Selenium Manager auto-locates the installed Chrome and driver
    return webdriver.Chrome(options=options)


def _get_page_html(url: str) -> str:
    import time
    driver = _build_driver()
    try:
        driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {
            "headers": {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"}
        })
        driver.get(url)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _TITLE_CSS))
            )
        except Exception:
            pass
        time.sleep(2)  # let JS-rendered widgets (price, stock) finish rendering
        return driver.page_source
    finally:
        driver.quit()


PRICE_CONTAINER_SELECTORS = [
    # "price to pay" widget — the actual checkout price, highest priority
    ".apex-pricetopay-value",
    # Core price containers (all three size variants Amazon uses)
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
    # Broad fallbacks
    ".a-price[data-a-size='xl']",
    ".a-price[data-a-size='b']",
    ".a-price[data-a-size='l']",
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
        text = container.get_text(strip=True)
        if text:
            currency = re.sub(r"[\d\s.,]", "", text).strip()
            digits = re.sub(r"[^\d.]", "", text.replace(",", ""))
            match = re.search(r"\d+\.?\d*", digits)
            if match:
                return float(match.group()), currency
    return None, ""


def _classify_page(soup) -> str:
    """Return a human-readable reason why the product title wasn't found."""
    text = soup.get_text(" ", strip=True).lower()
    if "captcha" in text or "robot" in text or "automated" in text:
        return "Amazon showed a CAPTCHA / robot-check page. Try again in a few seconds."
    if "sign in" in text and "password" in text:
        return "Amazon redirected to a sign-in page — this product may require a logged-in session."
    if "unavailable" in text or "page not found" in text or "doesn't exist" in text:
        return "Product page not found — the URL may be incorrect or the listing removed."
    return "Could not find product title. Amazon may have served a different page layout."


def scrape_product(url: str) -> dict:
    import time
    clean_url = _normalize_url(url)

    for attempt in range(2):
        try:
            html = _get_page_html(clean_url)
        except Exception as e:
            return {"name": None, "price": None, "currency": "", "stock": None, "url": clean_url, "error": str(e)}

        soup = BeautifulSoup(html, "lxml")
        name_el = next(
            (soup.select_one(sel) for sel in _TITLE_SELECTORS if soup.select_one(sel)),
            None,
        )
        name = name_el.get_text(strip=True) if name_el else None

        if name:
            break

        if attempt == 0:
            time.sleep(4)   # brief pause before retry

    if not name:
        return {
            "name": None, "price": None, "currency": "", "stock": None,
            "url": clean_url,
            "error": _classify_page(soup),
        }

    price, currency = _extract_price_and_currency(soup)

    stock_el = next(
        (soup.select_one(sel) for sel in STOCK_SELECTORS if soup.select_one(sel)),
        None,
    )
    stock = " ".join(stock_el.get_text().split()) if stock_el else "Unknown"

    return {"name": name, "price": price, "currency": currency, "stock": stock, "url": clean_url, "error": None}
