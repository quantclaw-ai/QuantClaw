"""Format events into human-readable notification messages."""
from __future__ import annotations

from quantclaw.events.types import Event

URGENCY_PREFIX = {
    "immediate": "[URGENT]",
    "high": "[ALERT]",
    "normal": "[INFO]",
    "low": "[LOG]",
}


def format_event(event: Event, urgency: str = "normal") -> str:
    prefix = URGENCY_PREFIX.get(urgency, "[INFO]")
    event_name = str(event.type).replace(".", " ").upper()
    payload_lines = [f"  {k}: {v}" for k, v in event.payload.items()]
    payload_str = "\n".join(payload_lines) if payload_lines else "  (no details)"
    return f"{prefix} {event_name}\n{payload_str}"
