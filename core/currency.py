"""Currency-label normalization.

Different scrapers report the same currency under different labels — Turkish Lira
comes back as "TL", "TRY", or "₺"; the US dollar as "USD" or "$". Left as-is, the
cart total (and any per-currency grouping) splits one real currency into phantom
buckets. Normalizing to a single canonical label per currency keeps prices and
totals consistent across sites. UI-agnostic so both the repositories (store-time)
and the display helpers (render-time) can use it.
"""

# Keys are compared upper-cased; values are the canonical label to display/store.
_CURRENCY_ALIASES = {
    "TRY": "TL", "TRL": "TL", "TL": "TL", "₺": "TL", "TURKISH LIRA": "TL",
    "USD": "$", "$": "$", "US$": "$",
    "EUR": "€", "€": "€",
    "GBP": "£", "£": "£",
}


def normalize_currency(currency) -> str:
    """Canonical label for a currency (e.g. 'TRY' -> 'TL'). Unknown labels are
    returned trimmed but otherwise unchanged; empty/None becomes ''."""
    if not currency:
        return ""
    key = str(currency).strip()
    return _CURRENCY_ALIASES.get(key.upper(), key)
