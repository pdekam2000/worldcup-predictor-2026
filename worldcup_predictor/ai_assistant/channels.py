"""Notification channel abstraction — Phase A19 (in-app now, extensible later)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class NotificationChannel(ABC):
    name: str

    @abstractmethod
    def deliver(self, user_id: str, notification: dict[str, Any]) -> bool:
        ...


class InAppChannel(NotificationChannel):
    name = "in_app"

    def deliver(self, user_id: str, notification: dict[str, Any]) -> bool:
        # Persisted by store before delivery; in-app is always "delivered" on write.
        return True


class EmailChannel(NotificationChannel):
    name = "email"

    def deliver(self, user_id: str, notification: dict[str, Any]) -> bool:
        # Future: wire to worldcup_predictor.notifications.send_email
        return False


class PushChannel(NotificationChannel):
    name = "push"

    def deliver(self, user_id: str, notification: dict[str, Any]) -> bool:
        return False


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def deliver(self, user_id: str, notification: dict[str, Any]) -> bool:
        return False


class DiscordChannel(NotificationChannel):
    name = "discord"

    def deliver(self, user_id: str, notification: dict[str, Any]) -> bool:
        return False


_CHANNELS: dict[str, NotificationChannel] = {
    "in_app": InAppChannel(),
    "email": EmailChannel(),
    "push": PushChannel(),
    "telegram": TelegramChannel(),
    "discord": DiscordChannel(),
}


def get_channel(name: str) -> NotificationChannel | None:
    return _CHANNELS.get(name)


def deliver_notification(
    user_id: str,
    notification: dict[str, Any],
    *,
    enabled_channels: list[str] | None = None,
) -> list[str]:
    channels = enabled_channels or ["in_app"]
    delivered: list[str] = []
    for ch_name in channels:
        ch = get_channel(ch_name)
        if ch and ch.deliver(user_id, notification):
            delivered.append(ch_name)
    return delivered
