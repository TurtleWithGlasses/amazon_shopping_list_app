"""Channel-agnostic notification dispatch.

A channel is any object with `send(title, message)`. The tray channel exists
now; a Telegram channel plugs in during Phase 15.
"""
from typing import List


class NotificationService:
    def __init__(self):
        self._channels: List = []

    def add_channel(self, channel) -> None:
        self._channels.append(channel)

    def notify(self, title: str, message: str) -> None:
        if not message:
            return
        for channel in self._channels:
            try:
                channel.send(title, message)
            except Exception:
                pass  # a broken channel must never break the others
