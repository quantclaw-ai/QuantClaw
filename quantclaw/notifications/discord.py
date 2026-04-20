"""Discord notification sink."""
from __future__ import annotations

import aiohttp


class DiscordSink:
    def __init__(self, webhook_url: str):
        self._url = webhook_url

    async def send(self, message: str):
        async with aiohttp.ClientSession() as session:
            await session.post(self._url, json={"content": message})
