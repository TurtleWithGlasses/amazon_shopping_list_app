"""Shared display formatting helpers."""
from core.currency import normalize_currency

_PREFIX_SYMBOLS = {"$", "€", "£", "¥", "₺", "₹"}


def format_price(price, currency: str) -> str:
    """'1,234.56 TL' / '$1,234.56' / 'N/A'. Normalizes the currency label so the
    same currency always renders identically (e.g. 'TRY' shows as 'TL')."""
    if price is None:
        return "N/A"
    currency = normalize_currency(currency)
    formatted = f"{price:,.2f}"
    if currency in _PREFIX_SYMBOLS:
        return f"{currency}{formatted}"
    return f"{formatted} {currency}" if currency else formatted
