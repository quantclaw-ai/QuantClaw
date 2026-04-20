import pytest
import asyncio

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType


class MockAgent(BaseAgent):
    name = "mock"
    model = "sonnet"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        if task.get("fail"):
            return AgentResult(status=AgentStatus.FAILED, error="intentional failure")
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "ok"})

    async def verify(self, result: AgentResult) -> bool:
        return result.status == AgentStatus.SUCCESS


def test_agent_run_success():
    bus = EventBus()
    agent = MockAgent(bus=bus, config={})
    result = asyncio.run(agent.run({"task": "test"}))
    assert result.status == AgentStatus.SUCCESS


def test_agent_run_failure_emits_event():
    bus = EventBus()
    events = []

    async def capture(e):
        events.append(e)

    async def run():
        bus.subscribe(EventType.AGENT_TASK_FAILED, capture)
        agent = MockAgent(bus=bus, config={})
        result = await agent.run({"fail": True})
        await asyncio.sleep(0.1)
        return result

    result = asyncio.run(run())
    assert result.status == AgentStatus.FAILED
    assert len(events) == 1


def test_agent_verify_fix_loop():
    call_count = 0

    class FlakyAgent(BaseAgent):
        name = "flaky"
        model = "opus"
        daemon = False

        async def execute(self, task: dict) -> AgentResult:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return AgentResult(status=AgentStatus.FAILED, error="flaky")
            return AgentResult(status=AgentStatus.SUCCESS, data={})

        async def verify(self, result: AgentResult) -> bool:
            return result.status == AgentStatus.SUCCESS

    bus = EventBus()
    agent = FlakyAgent(bus=bus, config={})
    result = asyncio.run(agent.run({"task": "flaky_test"}))
    assert result.status == AgentStatus.SUCCESS
    assert call_count == 3
