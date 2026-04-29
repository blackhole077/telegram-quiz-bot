"""Telegram bot configuration extending the base settings."""

from __future__ import annotations

from core.config import Settings


class BotSettings(Settings):
    """Runtime configuration for the Telegram bot frontend."""

    telegram_bot_token: str
    allowed_user_id: int


bot_settings = BotSettings()
