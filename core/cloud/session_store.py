"""Remember a login across launches by storing the Supabase *refresh token*
(never the password) in the OS credential store via keyring.

On Windows this is the Credential Manager. All calls degrade gracefully if no
keyring backend is available — "remember me" simply won't persist.
"""
_SERVICE = "PriceTracker"
_TOKEN_KEY = "refresh_token"
_EMAIL_KEY = "email"


def _keyring():
    import keyring
    return keyring


def save_session(refresh_token: str, email: str = "") -> None:
    if not refresh_token:
        return
    try:
        kr = _keyring()
        kr.set_password(_SERVICE, _TOKEN_KEY, refresh_token)
        kr.set_password(_SERVICE, _EMAIL_KEY, email or "")
    except Exception:
        pass


def load_refresh_token():
    try:
        return _keyring().get_password(_SERVICE, _TOKEN_KEY)
    except Exception:
        return None


def load_email():
    try:
        return _keyring().get_password(_SERVICE, _EMAIL_KEY)
    except Exception:
        return None


def clear_session() -> None:
    """Forget the saved login token (require re-login). The email is kept so the
    login form can still prefill it — it's not sensitive and saves retyping."""
    try:
        kr = _keyring()
        kr.delete_password(_SERVICE, _TOKEN_KEY)
    except Exception:
        pass


def has_saved_session() -> bool:
    return bool(load_refresh_token())
