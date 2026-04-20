"""Agent pool: registry and instantiation."""
from __future__ import annotations

from typing import Type

from quantclaw.agents.base import BaseAgent
from quantclaw.events.bus import EventBus


class AgentPool:
    def __init__(self, bus: EventBus, config: dict):
        self._bus = bus
        self._config = config
        self._registry: dict[str, Type[BaseAgent]] = {}
        self._instances: dict[str, BaseAgent] = {}

    def register(self, name: str, agent_cls: Type[BaseAgent]):
        self._registry[name] = agent_cls

    def get(self, name: str) -> BaseAgent | None:
        if name not in self._instances and name in self._registry:
            self._instances[name] = self._registry[name](
                bus=self._bus, config=self._config
            )
        return self._instances.get(name)

    def list_agents(self) -> list[str]:
        return list(self._registry.keys())
