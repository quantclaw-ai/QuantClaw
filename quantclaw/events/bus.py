"""Async event bus with publish/subscribe and wildcard matching."""
from __future__ import annotations
import asyncio
import fnmatch
from collections import defaultdict
from typing import Callable, Awaitable
from quantclaw.events.types import Event, EventType

Handler = Callable[[Event], Awaitable[None]]

class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []

    def subscribe(self, pattern: str | EventType, handler: Handler):
        key = str(pattern)
        self._handlers[key].append(handler)

    def unsubscribe(self, pattern: str | EventType, handler: Handler):
        key = str(pattern)
        if key in self._handlers:
            self._handlers[key] = [h for h in self._handlers[key] if h != handler]

    async def publish(self, event: Event):
        self._history.append(event)
        if len(self._history) > 10000:
            self._history = self._history[-5000:]
        event_str = str(event.type)
        for pattern, handlers in self._handlers.items():
            if fnmatch.fnmatch(event_str, pattern) or pattern == event_str:
                for handler in handlers:
                    task = asyncio.create_task(handler(event))
                    task.add_done_callback(self._on_task_error)

    def _on_task_error(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            import logging
            logging.getLogger(__name__).error("Event handler failed: %s", exc)

    def recent(self, n: int = 50) -> list[Event]:
        return self._history[-n:]
