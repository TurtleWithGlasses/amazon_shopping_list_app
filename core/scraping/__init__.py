"""Pluggable, multi-retailer scraping.

Public API:
    from core.scraping import scrape, ProductData
    result = scrape("https://www.amazon.com.tr/dp/...")
"""
from .base import ProductData, RetailerAdapter
from .registry import get_adapter, register, scrape, supported_retailers

__all__ = [
    "ProductData",
    "RetailerAdapter",
    "scrape",
    "register",
    "get_adapter",
    "supported_retailers",
]
