"""Scraping contracts shared by every retailer adapter."""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .browser import fetch_with_requests, get_page_html


@dataclass
class ProductData:
    """Normalized result of scraping one product page.

    `error` is set (and the other fields left empty) when scraping fails, so
    callers can branch on `result.error` rather than catching exceptions.
    """
    url: str
    name: Optional[str] = None
    price: Optional[float] = None
    currency: str = ""
    stock: Optional[str] = None
    image_url: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.name is not None


class RetailerAdapter(ABC):
    """One implementation per supported store (Amazon, then others).

    Subclasses implement `_parse(html, clean_url)` (pure parsing) and declare the
    Selenium wait hints below. `scrape()` is a shared template that tries a fast
    plain-HTTP fetch first and only launches headless Chrome when the initial
    HTML doesn't already contain the data (Phase 21 performance work).
    """

    #: short, stable identifier stored on Product.retailer (e.g. "amazon")
    name: str = "unknown"

    # --- Selenium fallback hints (overridden per adapter) ------------------
    wait_css: Optional[str] = None        # wait until this element is present
    wait_text_css: Optional[str] = None   # wait until this element has text
    settle_seconds: float = 2.0           # extra settle time after waits
    selenium_attempts: int = 1            # re-fetch tries when parsing fails
    selenium_retry_sleep: float = 0.0     # pause between those tries

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Return True if this adapter can handle the given product URL."""

    @abstractmethod
    def normalize_url(self, url: str) -> str:
        """Strip tracking/session params down to a canonical product URL."""

    @abstractmethod
    def _parse(self, html: str, clean_url: str) -> ProductData:
        """Parse already-fetched HTML into a ProductData (no network)."""

    def _is_complete(self, data: ProductData) -> bool:
        """Whether a fast-path (HTTP) result is good enough to skip Chrome.

        Default: a usable name *and* a price. Sites whose price is only injected
        by JS will fail this and correctly fall back to Selenium.
        """
        return data.ok and data.price is not None

    def scrape(self, url: str) -> ProductData:
        clean_url = self.normalize_url(url)

        # 1) Fast path: plain HTTP, no browser. Works whenever the price is in
        #    the initial HTML (embedded JSON, microdata, JSON-LD, server-rendered
        #    DOM). ~100x faster than launching Chrome.
        html = fetch_with_requests(clean_url)
        if html:
            try:
                data = self._parse(html, clean_url)
            except Exception:
                data = None
            if data is not None and self._is_complete(data):
                return data

        # 2) Fallback: headless Chrome renders JS-driven values.
        data = None
        for attempt in range(max(1, self.selenium_attempts)):
            try:
                html = get_page_html(
                    clean_url, wait_css=self.wait_css,
                    wait_text_css=self.wait_text_css,
                    settle_seconds=self.settle_seconds,
                )
            except Exception as exc:
                return ProductData(url=clean_url, error=str(exc))
            data = self._parse(html, clean_url)
            if data.ok:
                return data
            if attempt + 1 < self.selenium_attempts and self.selenium_retry_sleep:
                time.sleep(self.selenium_retry_sleep)
        return data  # last parse — carries the adapter's error message
