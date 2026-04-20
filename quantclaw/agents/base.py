"""Base agent class with verify-fix loop."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType


class AgentStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class AgentResult:
    status: AgentStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class BaseAgent(ABC):
    name: str = "base"
    model: str = "opus"
    daemon: bool = False
    max_retries: int = 3

    def __init__(self, bus: EventBus, config: dict):
        self._bus = bus
        self._config = config

    @property
    def manifest(self):
        """Access the full agent manifest — who exists, what they need/produce."""
        from quantclaw.agents.manifest import get_manifest
        return get_manifest()

    @property
    def my_spec(self):
        """This agent's spec from the manifest."""
        from quantclaw.agents.manifest import get_spec
        return get_spec(self.name)

    @property
    def peers(self):
        """Agents this agent directly collaborates with."""
        from quantclaw.agents.manifest import get_peers
        return get_peers(self.name)

    def manifest_for_prompt(self) -> str:
        """Format the manifest for LLM prompt inclusion, highlighting this agent."""
        from quantclaw.agents.manifest import format_manifest_for_prompt
        return format_manifest_for_prompt(self.name)

    @abstractmethod
    async def execute(self, task: dict) -> AgentResult:
        ...

    async def verify(self, result: AgentResult) -> bool:
        return result.status == AgentStatus.SUCCESS

    async def plan(self, task: dict) -> list[dict]:
        return [task]

    async def on_event(self, event: Event) -> None:
        pass

    async def on_failure(self, error: str) -> None:
        pass

    async def run(self, task: dict) -> AgentResult:
        await self._bus.publish(Event(
            type=EventType.AGENT_TASK_STARTED,
            payload={"agent": self.name, "task": str(task)},
            source_agent=self.name,
        ))

        last_result = AgentResult(status=AgentStatus.FAILED, error="no attempts made")

        for attempt in range(1, self.max_retries + 1):
            last_result = await self.execute(task)

            if await self.verify(last_result):
                await self._bus.publish(Event(
                    type=EventType.AGENT_TASK_COMPLETED,
                    payload={"agent": self.name, "result": last_result.data},
                    source_agent=self.name,
                ))
                return last_result

            if attempt < self.max_retries:
                await self.on_failure(last_result.error)

        # All retries exhausted
        await self._bus.publish(Event(
            type=EventType.AGENT_TASK_FAILED,
            payload={"agent": self.name, "error": last_result.error, "attempts": self.max_retries},
            source_agent=self.name,
        ))
        return last_result
