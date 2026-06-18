"""Load Supabase credentials.

Lookup order:
  1. Environment variables SUPABASE_URL / SUPABASE_ANON_KEY
  2. config.local.json in the project root (git-ignored, for development)
  3. config.json in the app-data directory (for an installed app)

The anon key is safe to ship in a client — row-level security is what protects
data. The service-role key must NEVER be placed in any of these files.
"""
import json
import os
from pathlib import Path
from typing import Optional, Tuple

from core.paths import app_data_dir

ENV_URL = "SUPABASE_URL"
ENV_KEY = "SUPABASE_ANON_KEY"


def _config_files():
    return [Path("config.local.json"), app_data_dir() / "config.json"]


def load_supabase_config() -> Tuple[Optional[str], Optional[str]]:
    url = os.environ.get(ENV_URL)
    key = os.environ.get(ENV_KEY)
    if url and key:
        return url, key

    for path in _config_files():
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                url = data.get("supabase_url")
                key = data.get("supabase_anon_key")
                if url and key:
                    return url, key
        except Exception:
            continue
    return None, None


def is_configured() -> bool:
    url, key = load_supabase_config()
    return bool(url and key)
