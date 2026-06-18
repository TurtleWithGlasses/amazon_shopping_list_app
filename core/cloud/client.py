"""Lazily-created Supabase client shared across the app."""
from functools import lru_cache

from .config import is_configured, load_supabase_config


@lru_cache(maxsize=1)
def get_client():
    """Return a singleton Supabase client, or raise if not configured."""
    from supabase import create_client

    url, key = load_supabase_config()
    if not (url and key):
        raise RuntimeError(
            "Supabase is not configured. Copy config.example.json to "
            "config.local.json and fill in your project URL + anon key "
            "(see SUPABASE_SETUP.md)."
        )
    return create_client(url, key)


def connection_ok() -> bool:
    """Best-effort connectivity check (RLS returns no rows when unauthenticated)."""
    if not is_configured():
        return False
    try:
        get_client().table("products").select("id").limit(1).execute()
        return True
    except Exception:
        return False
