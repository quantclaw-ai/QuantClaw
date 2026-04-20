"""Batched event persistence to SQLite."""
from __future__ import annotations
import asyncio
import json
from quantclaw.events.types import Event
from quantclaw.state.db import StateDB


class EventPersister:
    """Buffers events and flushes to SQLite every flush_interval seconds."""

    def __init__(self, db: StateDB, flush_interval: float = 5.0):
        self._db = db
        self._flush_interval = flush_interval
        self._buffer: list[Event] = []
        self._task: asyncio.Task | None = None

    async def handle_event(self, event: Event) -> None:
        self._buffer.append(event)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        for event in batch:
            await self._db.conn.execute(
                "INSERT INTO events (event_type, payload, source_agent) VALUES (?, ?, ?)",
                (str(event.type), json.dumps(event.payload), event.source_agent),
            )
        await self._db.conn.commit()

    def start(self) -> None:
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush()
