"""Shared timescale options for graphs and exports."""
from datetime import datetime, timedelta
from typing import Optional

from core.models import utcnow

# Ordered for display in dropdowns.
TIMESCALES = {
    "1 Day": timedelta(days=1),
    "1 Week": timedelta(weeks=1),
    "1 Month": timedelta(days=30),
    "3 Months": timedelta(days=90),
    "All time": None,
}
TIMESCALE_LABELS = list(TIMESCALES.keys())
DEFAULT_TIMESCALE = "All time"


def since_for(label: str) -> Optional[datetime]:
    """Return the UTC cutoff for a timescale label, or None for 'All time'."""
    delta = TIMESCALES.get(label)
    return None if delta is None else utcnow() - delta
