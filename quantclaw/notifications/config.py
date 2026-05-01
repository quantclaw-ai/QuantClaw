"""Notification configuration helpers."""
from __future__ import annotations

from typing import Any

CHANNELS = ("telegram", "discord", "slack")


def is_configured_value(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.startswith("$")


def is_channel_configured(channel: str, config: dict[str, Any]) -> bool:
    notifications = config.get("notifications", {})
    channel_config = notifications.get(channel, {})
    if channel == "telegram":
        return (
            is_configured_value(channel_config.get("bot_token"))
            and is_configured_value(channel_config.get("chat_id"))
        )
    if channel in ("discord", "slack"):
        return is_configured_value(channel_config.get("webhook_url"))
    return False


def configured_channels(config: dict[str, Any]) -> dict[str, bool]:
    return {channel: is_channel_configured(channel, config) for channel in CHANNELS}


def build_notification_sinks(config: dict[str, Any]) -> dict[str, Any]:
    """Build only fully configured sinks."""
    from quantclaw.notifications.telegram import TelegramSink
    from quantclaw.notifications.discord import DiscordSink
    from quantclaw.notifications.slack import SlackSink

    notifications = config.get("notifications", {})
    sinks: dict[str, Any] = {}

    if is_channel_configured("telegram", config):
        telegram = notifications["telegram"]
        sinks["telegram"] = TelegramSink(telegram["bot_token"], telegram["chat_id"])
    if is_channel_configured("discord", config):
        sinks["discord"] = DiscordSink(notifications["discord"]["webhook_url"])
    if is_channel_configured("slack", config):
        sinks["slack"] = SlackSink(notifications["slack"]["webhook_url"])

    return sinks
