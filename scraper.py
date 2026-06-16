import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _normalize_url(url: str) -> str:
    """Strip session/referral query params, keep only /dp/{ASIN}."""
    parsed = urlparse(url)
    match = re.search(r"/dp/([A-Z0-9]{10})", parsed.path, re.IGNORECASE)
    if match:
        return f"{parsed.scheme}://{parsed.netloc}/dp/{match.group(1)}"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


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
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    # Use system Chromium installed via packages.txt — no runtime download needed
    options.binary_location = "/usr/bin/chromium"
    return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)


def _get_page_html(url: str) -> str:
    driver = _build_driver()
    try:
        driver.get(url)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "productTitle"))
            )
        except Exception:
            pass
        return driver.page_source
    finally:
        driver.quit()


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
        None,
    )
    stock = " ".join(stock_el.get_text().split()) if stock_el else "Unknown"

    if not name:
        return {
            "name": None, "price": None, "currency": "", "stock": None,
            "url": clean_url,
            "error": "Could not parse product — page may have been blocked or shown a CAPTCHA.",
        }

    return {"name": name, "price": price, "currency": currency, "stock": stock, "url": clean_url, "error": None}
