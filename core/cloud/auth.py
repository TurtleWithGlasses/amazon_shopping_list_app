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


def send_password_reset(email: str):
    """Email a password-reset code (Supabase recovery). The 'Reset Password' email
    template must include the 6-digit `{{ .Token }}` so the in-app flow can verify
    it. Neutral — never reveals whether the address has an account."""
    return get_client().auth.reset_password_for_email(email)


def verify_recovery_otp(email: str, token: str):
    """Verify the recovery code from the reset email, opening a short session so
    the password can then be changed via update_password()."""
    global _current_user
    response = get_client().auth.verify_otp(
        {"email": email, "token": token, "type": "recovery"}
    )
    _current_user = response.user
    return response


def restore_session(refresh_token: str):
    """Re-establish a session from a stored refresh token (for auto-login).
    Raises on an invalid/expired token. Returns the gotrue response."""
    global _current_user
    response = get_client().auth.refresh_session(refresh_token)
    _current_user = response.user
    return response


def current_refresh_token():
    """The current session's refresh token, or None. Note Supabase rotates
    refresh tokens on use, so re-save it after restoring a session."""
    try:
        session = get_client().auth.get_session()
        return session.refresh_token if session else None
    except Exception:
        return None


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


def _update_user(attributes: dict):
    global _current_user
    response = get_client().auth.update_user(attributes)
    if response and response.user:
        _current_user = response.user
    return response


def update_profile(first_name: str, last_name: str):
    """Update the user's first/last name (stored in user metadata)."""
    return _update_user({"data": {"first_name": first_name, "last_name": last_name}})


def update_password(new_password: str):
    """Change the password immediately for the logged-in user."""
    return _update_user({"password": new_password})


def update_email(new_email: str):
    """Request an email change; Supabase emails a confirmation to the new address."""
    return _update_user({"email": new_email})


def is_logged_in() -> bool:
    return _current_user is not None
