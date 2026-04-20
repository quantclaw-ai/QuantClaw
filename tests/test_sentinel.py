"""Tests for Sentinel monitoring agent."""
import asyncio
import pytest
from quantclaw.agents.sentinel import SentinelAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType


def test_sentinel_interface():
    bus = EventBus()
    agent = SentinelAgent(bus=bus, config={})
    assert agent.name == "sentinel"
    assert agent.daemon is True


def test_sentinel_status_report():
    bus = EventBus()
    agent = SentinelAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({})
        assert result.status == AgentStatus.SUCCESS
        assert "active_rules" in result.data
        assert result.data["active_rules"] == 4  # 4 default rules

    asyncio.run(_run())


def test_sentinel_detects_failure_streak():
    bus = EventBus()
    agent = SentinelAgent(bus=bus, config={})

    narratives = []
    async def capture(event):
        if str(event.type) == "chat.narrative":
            narratives.append(event.payload.get("message", ""))
    bus.subscribe("chat.*", capture)

    async def _run():
        # Fire 3 failures for the same agent
        for i in range(3):
            await agent.on_event(Event(
                type=EventType.AGENT_TASK_FAILED,
                payload={"agent": "validator", "error": "failed"},
                source_agent="validator",
            ))
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    assert len(narratives) >= 1
    assert "validator" in narratives[0]
    assert "3 times" in narratives[0]


def test_sentinel_resets_on_success():
    bus = EventBus()
    agent = SentinelAgent(bus=bus, config={})

    async def _run():
        # 2 failures
        for i in range(2):
            await agent.on_event(Event(
                type=EventType.AGENT_TASK_FAILED,
                payload={"agent": "miner", "error": "failed"},
                source_agent="miner",
            ))
        # 1 success resets the count
        await agent.on_event(Event(
            type=EventType.AGENT_TASK_COMPLETED,
            payload={"agent": "miner"},
            source_agent="miner",
        ))
        assert agent._failure_counts["miner"] == 0

    asyncio.run(_run())


def test_sentinel_cost_warning():
    bus = EventBus()
    agent = SentinelAgent(bus=bus, config={})

    narratives = []
    async def capture(event):
        if str(event.type) == "chat.narrative":
            narratives.append(event.payload.get("message", ""))
    bus.subscribe("chat.*", capture)

    async def _run():
        await agent.on_event(Event(
            type=EventType.COST_BUDGET_WARNING,
            payload={"spent": 95.0, "budget": 100.0},
            source_agent="cost_tracker",
        ))
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    assert len(narratives) >= 1
    assert "budget" in narratives[0].lower()


def test_sentinel_market_gap():
    bus = EventBus()
    agent = SentinelAgent(bus=bus, config={})

    narratives = []
    async def capture(event):
        if str(event.type) == "chat.narrative":
            narratives.append(event.payload.get("message", ""))
    bus.subscribe("chat.*", capture)

    async def _run():
        await agent.on_event(Event(
            type=EventType.MARKET_GAP_DETECTED,
            payload={"symbol": "TSLA", "gap_pct": -0.08},
            source_agent="sentinel",
        ))
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    assert len(narratives) >= 1
    assert "TSLA" in narratives[0]
