"""Shared display formatting helpers."""

_PREFIX_SYMBOLS = {"$", "€", "£", "¥", "₺", "₹"}


def format_price(price, currency: str) -> str:
    """'1,234.56 TL' / '$1,234.56' / 'N/A'."""
    if price is None:
        return "N/A"
    formatted = f"{price:,.2f}"
    if currency in _PREFIX_SYMBOLS:
        return f"{currency}{formatted}"
    return f"{formatted} {currency}" if currency else formatted
