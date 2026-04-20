"""Tests for iterative run_cycle with evaluate loop."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool


class StubAgent(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.5, "result": "data"})


def _make(tmp_path):
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    config = {
        "orchestration": {
            "max_iterations_per_cycle": 3,
            "exploration": {
                "explore_temp": 0.7,
                "exploit_temp": 0.2,
                "balanced_temp": 0.4,
                "high_explore_until": 5,
                "balanced_until": 15,
            },
        },
    }
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT),
                    dispatcher=dispatcher, config=config)
    return bus, pb, ooda


def test_iterative_cycle_runs(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    events = []
    async def capture(event):
        events.append(str(event.type))
    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        await asyncio.sleep(0.1)

    asyncio.run(_run())
    assert "orchestration.evaluation" in events
    assert "orchestration.cycle_complete" in events


def test_iterative_cycle_clears_context(tmp_path):
    _, _, ooda = _make(tmp_path)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle()
        assert len(ooda._iteration_context) == 0

    asyncio.run(_run())


def test_iterative_cycle_enriched_events(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    payloads = []
    async def capture(event):
        if str(event.type) == "orchestration.cycle_complete":
            payloads.append(event.payload)
    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle()
        await asyncio.sleep(0.1)

    asyncio.run(_run())
    assert len(payloads) >= 1
    p = payloads[0]
    assert "iterations" in p
    assert "llm_calls" in p
    assert "exploration_mode" in p
