"""Interpret free-text stock strings (Turkish + English) for charting.

classify_stock() maps a stock message to a discrete availability level plus an
optional quantity, so stock history can be drawn as a step chart.
"""
import re
from typing import Optional, Tuple

OUT_OF_STOCK = 0
LIMITED = 1
IN_STOCK = 2

LEVEL_LABELS = {OUT_OF_STOCK: "Out", LIMITED: "Limited", IN_STOCK: "In stock"}

_OUT_WORDS = (
    "tükendi", "tukendi", "stokta yok", "out of stock",
    "currently unavailable", "unavailable", "mevcut değil", "mevcut degil",
)
_LIMITED_WORDS = ("sadece", "kaldı", "kaldi", "only", "left in stock")
_IN_WORDS = ("stokta var", "in stock", "available", "mevcut")


def extract_quantity(text: str) -> Optional[int]:
    t = text.casefold()
    for pattern in (r"(\d+)\s*adet", r"(?:sadece|only)\s*(\d+)", r"(\d+)\s*left"):
        match = re.search(pattern, t)
        if match:
            return int(match.group(1))
    return None


def classify_stock(text: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Return (level, quantity). level is None for unknown/unrecognized text."""
    if not text:
        return (None, None)
    t = text.casefold().strip()
    if t in ("unknown", "bilinmiyor", "-", ""):
        return (None, None)
    quantity = extract_quantity(t)
    if any(w in t for w in _OUT_WORDS):
        return (OUT_OF_STOCK, quantity)
    if quantity is not None or any(w in t for w in _LIMITED_WORDS):
        return (LIMITED, quantity)
    if any(w in t for w in _IN_WORDS):
        return (IN_STOCK, quantity)
    return (None, None)
