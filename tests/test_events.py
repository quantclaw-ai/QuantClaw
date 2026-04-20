import pytest
import asyncio
from quantclaw.events.types import Event, EventType
from quantclaw.events.bus import EventBus

def test_event_creation():
    e = Event(type=EventType.MARKET_GAP_DETECTED, payload={"gap": -0.015, "ticker": "SPY"})
    assert e.type == EventType.MARKET_GAP_DETECTED
    assert e.payload["gap"] == -0.015

def test_event_bus_publish_subscribe():
    bus = EventBus()
    received = []

    async def handler(event: Event):
        received.append(event)

    async def run():
        bus.subscribe(EventType.AGENT_TASK_COMPLETED, handler)
        await bus.publish(Event(type=EventType.AGENT_TASK_COMPLETED, payload={"agent": "miner"}))
        await asyncio.sleep(0.1)

    asyncio.run(run())
    assert len(received) == 1
    assert received[0].payload["agent"] == "miner"

def test_event_bus_wildcard():
    bus = EventBus()
    received = []

    async def handler(event: Event):
        received.append(event)

    async def run():
        bus.subscribe("agent.*", handler)
        await bus.publish(Event(type=EventType.AGENT_TASK_STARTED, payload={}))
        await bus.publish(Event(type=EventType.AGENT_TASK_FAILED, payload={}))
        await bus.publish(Event(type=EventType.MARKET_GAP_DETECTED, payload={}))
        await asyncio.sleep(0.1)

    asyncio.run(run())
    assert len(received) == 2

def test_orchestration_event_types():
    """Verify orchestration event types exist."""
    from quantclaw.events.types import EventType
    assert EventType.ORCHESTRATION_PLAN_CREATED == "orchestration.plan_created"
    assert EventType.ORCHESTRATION_STEP_STARTED == "orchestration.step_started"
    assert EventType.ORCHESTRATION_STEP_COMPLETED == "orchestration.step_completed"
    assert EventType.ORCHESTRATION_STEP_FAILED == "orchestration.step_failed"
    assert EventType.ORCHESTRATION_BROADCAST == "orchestration.broadcast"
    assert EventType.PLAYBOOK_ENTRY_ADDED == "playbook.entry_added"
    assert EventType.TRUST_LEVEL_CHANGED == "trust.level_changed"
