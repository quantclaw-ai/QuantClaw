"""Event-to-notification routing loaded from YAML config."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass

@dataclass
class Route:
    event_pattern: str
    channels: list[str]
    urgency: str

class EventRouter:
    def __init__(self, routes: list[Route]):
        self._routes = routes

    @classmethod
    def from_config(cls, config: dict) -> EventRouter:
        routes = []
        for entry in config.get("notification_routes", []):
            routes.append(Route(
                event_pattern=entry["event"],
                channels=entry["channels"],
                urgency=entry.get("urgency", "normal"),
            ))
        return cls(routes)

    def get_routes(self, event_type: str) -> list[Route]:
        return [r for r in self._routes if fnmatch.fnmatch(event_type, r.event_pattern)]
