"""Scraping contracts shared by every retailer adapter."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


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
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.name is not None


class RetailerAdapter(ABC):
    """One implementation per supported store (Amazon, then others)."""

    #: short, stable identifier stored on Product.retailer (e.g. "amazon")
    name: str = "unknown"

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Return True if this adapter can handle the given product URL."""

    @abstractmethod
    def normalize_url(self, url: str) -> str:
        """Strip tracking/session params down to a canonical product URL."""

    @abstractmethod
    def scrape(self, url: str) -> ProductData:
        """Fetch and parse the product page into a ProductData."""
