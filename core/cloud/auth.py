"""Supabase Auth: register (with email confirmation), login, logout."""
from typing import Optional

from .client import get_client

_current_user = None  # gotrue User object for the logged-in session


def sign_up(email: str, password: str, first_name: str = "", last_name: str = ""):
    """Create an account. Supabase emails a confirmation link; the user must
    click it before they can log in. First/last name are stored in the user's
    metadata. Returns the gotrue response."""
    return get_client().auth.sign_up({
        "email": email,
        "password": password,
        "options": {"data": {"first_name": first_name, "last_name": last_name}},
    })


def sign_in(email: str, password: str):
    """Log in with email + password. Raises AuthApiError on bad credentials or
    an unconfirmed email. On success, caches the user for the session."""
    global _current_user
    response = get_client().auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    _current_user = response.user
    return response


def sign_out() -> None:
    global _current_user
    try:
        get_client().auth.sign_out()
    finally:
        _current_user = None


def current_user_id() -> Optional[str]:
    return _current_user.id if _current_user else None


def current_email() -> Optional[str]:
    return _current_user.email if _current_user else None


def _metadata() -> dict:
    return (getattr(_current_user, "user_metadata", None) or {}) if _current_user else {}


def current_first_name() -> str:
    return _metadata().get("first_name", "") or ""


def current_last_name() -> str:
    return _metadata().get("last_name", "") or ""


def current_display_name() -> Optional[str]:
    """'First Last' if available, else the email, else None."""
    if not _current_user:
        return None
    full = f"{current_first_name()} {current_last_name()}".strip()
    return full or _current_user.email


def is_logged_in() -> bool:
    return _current_user is not None
