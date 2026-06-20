"""Telegram bot notifications.

Config: the bot token is sensitive → stored in the OS keyring; the chat ID and
the enabled flag live in QSettings. `TelegramNotifier` is a NotificationService
channel that self-gates (does nothing unless enabled + configured) and sends in
the background so the UI never blocks on the network.
"""
from PySide6.QtCore import QRunnable, QSettings, QThreadPool, Slot

_KR_SERVICE = "PriceTracker"
_KR_TOKEN = "telegram_token"
_S_CHAT = "telegram_chat_id"
_S_ENABLED = "telegram_enabled"
_API = "https://api.telegram.org/bot{token}/sendMessage"


def _keyring():
    import keyring
    return keyring


def save_token(token: str) -> None:
    try:
        kr = _keyring()
        if token:
            kr.set_password(_KR_SERVICE, _KR_TOKEN, token)
        else:
            try:
                kr.delete_password(_KR_SERVICE, _KR_TOKEN)
            except Exception:
                pass
    except Exception:
        pass


def load_token():
    try:
        return _keyring().get_password(_KR_SERVICE, _KR_TOKEN)
    except Exception:
        return None


def chat_id() -> str:
    return QSettings().value(_S_CHAT, "") or ""


def set_chat_id(value: str) -> None:
    QSettings().setValue(_S_CHAT, value or "")


def is_enabled() -> bool:
    return QSettings().value(_S_ENABLED, False, type=bool)


def set_enabled(value: bool) -> None:
    QSettings().setValue(_S_ENABLED, bool(value))


def is_configured() -> bool:
    return bool(load_token() and chat_id())


def _post(token: str, cid: str, text: str):
    import requests
    return requests.post(
        _API.format(token=token), data={"chat_id": cid, "text": text}, timeout=10
    )


def send_test(token: str, cid: str):
    """Synchronous test send. Returns (ok, error_message)."""
    if not token or not cid:
        return False, "Enter both a bot token and a chat ID."
    try:
        resp = _post(token, cid, "Price Tracker: test message ✅")
        if resp.status_code == 200 and resp.json().get("ok"):
            return True, ""
        return False, f"Telegram error: {resp.text[:200]}"
    except Exception as exc:
        return False, str(exc)


class _SendTask(QRunnable):
    def __init__(self, token, cid, text):
        super().__init__()
        self.token, self.cid, self.text = token, cid, text

    @Slot()
    def run(self) -> None:
        try:
            _post(self.token, self.cid, self.text)
        except Exception:
            pass


class TelegramNotifier:
    """NotificationService channel — self-gating, async."""

    def send(self, title: str, message: str) -> None:
        if not is_enabled():
            return
        token, cid = load_token(), chat_id()
        if not token or not cid:
            return
        text = f"{title}\n{message}" if message else title
        QThreadPool.globalInstance().start(_SendTask(token, cid, text))
