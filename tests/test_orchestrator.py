import asyncio

import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool


class EchoAgent(BaseAgent):
    name = "echo"
    model = "sonnet"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(
            status=AgentStatus.SUCCESS, data={"echo": task.get("msg", "")}
        )


def test_pool_register_and_get():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("echo", EchoAgent)
    agent = pool.get("echo")
    assert agent is not None
    assert agent.name == "echo"


def test_pool_list_agents():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("echo", EchoAgent)
    assert "echo" in pool.list_agents()


def test_dispatcher_routes_to_agent():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("echo", EchoAgent)
    dispatcher = Dispatcher(pool=pool)
    result = asyncio.run(dispatcher.dispatch("echo", {"msg": "hello"}))
    assert result.status == AgentStatus.SUCCESS
    assert result.data["echo"] == "hello"


def test_dispatcher_unknown_agent():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    dispatcher = Dispatcher(pool=pool)
    result = asyncio.run(dispatcher.dispatch("nonexistent", {}))
    assert result.status == AgentStatus.FAILED
    assert "Unknown agent" in result.error


def test_dispatcher_parallel():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("echo", EchoAgent)
    dispatcher = Dispatcher(pool=pool)
    results = asyncio.run(
        dispatcher.dispatch_parallel([
            ("echo", {"msg": "a"}),
            ("echo", {"msg": "b"}),
        ])
    )
    assert len(results) == 2
    assert all(r.status == AgentStatus.SUCCESS for r in results)
