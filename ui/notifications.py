"""UI notification channels (system tray)."""
from PySide6.QtWidgets import QSystemTrayIcon


class TrayChannel:
    def __init__(self, tray_icon):
        self._tray = tray_icon

    def send(self, title: str, message: str) -> None:
        if self._tray is not None and self._tray.isVisible():
            self._tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 8000
            )
