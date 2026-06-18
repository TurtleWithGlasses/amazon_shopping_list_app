"""Active data backend indirection.

The UI and services import this module (`from core import datastore as repo`)
and call e.g. `repo.list_products()`. By default it delegates to the local
SQLite repository; after a successful cloud login, `set_backend()` switches it
to the Supabase repository — no other code has to change.
"""
from core import repository as _local

_active = _local


def set_backend(module) -> None:
    global _active
    _active = module


def reset_backend() -> None:
    global _active
    _active = _local


def active_backend_name() -> str:
    return getattr(_active, "__name__", "unknown")


def __getattr__(name):
    # PEP 562: resolve repo.<func> against the active backend.
    return getattr(_active, name)
