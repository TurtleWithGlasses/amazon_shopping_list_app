"""Generic page-fetching infrastructure shared by all retailer adapters.

Selenium is primary because the displayed price/stock are JS-rendered; a plain
HTTP request is the Windows fallback when Chrome fails to start. This module is
retailer-agnostic — adapters pass their own `wait_css` selector.
"""
import sys
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_DEFAULT_ACCEPT_LANGUAGE = "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"

_REQUEST_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_with_requests(url: str) -> Optional[str]:
    """Fast HTTP fetch — works on residential IPs, no browser needed."""
    import requests
    try:
        resp = requests.get(url, headers=_REQUEST_HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def fetch_with_selenium(
    url: str,
    *,
    wait_css: Optional[str] = None,
    wait_text_css: Optional[str] = None,
    lang: str = "tr",
    accept_language: str = _DEFAULT_ACCEPT_LANGUAGE,
    settle_seconds: float = 2.0,
) -> str:
    """Headless browser fetch — renders JS-driven content (price, stock)."""
    options = Options()
    # No --user-data-dir: Selenium creates its own isolated temp profile.
    # Forcing a custom dir is a known cause of the Windows
    # "DevToolsActivePort file doesn't exist" startup crash.
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument(f"--lang={lang}")
    options.add_argument(f"--user-agent={_USER_AGENT}")

    if sys.platform.startswith("linux"):
        # Linux/container: system Chromium + container-only flags
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
    else:
        # Windows / macOS: Selenium Manager locates Chrome + chromedriver
        service = None

    # Chrome occasionally fails to start on the first try — retry before giving up.
    driver = None
    last_err = None
    for _ in range(3):
        try:
            driver = (webdriver.Chrome(service=service, options=options)
                      if service else webdriver.Chrome(options=options))
            break
        except Exception as exc:
            last_err = exc
            time.sleep(1.5)
    if driver is None:
        raise last_err

    try:
        driver.execute_cdp_cmd(
            "Network.setExtraHTTPHeaders",
            {"headers": {"Accept-Language": accept_language}},
        )
        driver.get(url)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        if wait_css:
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
                )
            except Exception:
                pass
        if wait_text_css:
            # Wait until a matching element has NON-EMPTY text — for values loaded
            # by a later XHR that show a skeleton placeholder until ready.
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: any(
                        e.text.strip() for e in d.find_elements(By.CSS_SELECTOR, wait_text_css)
                    )
                )
            except Exception:
                pass
        time.sleep(settle_seconds)  # let JS-rendered widgets finish
        return driver.page_source
    finally:
        driver.quit()


def get_page_html(url: str, *, wait_css: Optional[str] = None,
                  wait_text_css: Optional[str] = None, settle_seconds: float = 2.0) -> str:
    """Selenium-primary fetch with a requests fallback on Windows Chrome failure."""
    kwargs = dict(wait_css=wait_css, wait_text_css=wait_text_css, settle_seconds=settle_seconds)
    if sys.platform.startswith("linux"):
        return fetch_with_selenium(url, **kwargs)
    try:
        return fetch_with_selenium(url, **kwargs)
    except Exception:
        html = fetch_with_requests(url)
        if html:
            return html
        raise
