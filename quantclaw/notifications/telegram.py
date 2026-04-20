"""Telegram notification sink."""
from __future__ import annotations

import aiohttp


class TelegramSink:
    def __init__(self, bot_token: str, chat_id: str):
        self._token = bot_token
        self._chat_id = chat_id

    async def send(self, message: str):
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"chat_id": self._chat_id, "text": message, "parse_mode": "Markdown"})
