"""Tests for OODA activation: run_cycle, run_continuous, cycle limits."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
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
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "found data"})


def _make(tmp_path, mode=AutonomyMode.AUTOPILOT):
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=mode),
                    dispatcher=dispatcher, config={})
    return bus, pb, ooda


def test_run_cycle_completes(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    async def _run():
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        assert ooda.phase == OODAPhase.SLEEP

    asyncio.run(_run())


def test_run_cycle_emits_cycle_complete(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    events = []
    async def capture(event):
        events.append(str(event.type))
    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        await asyncio.sleep(0.1)

    asyncio.run(_run())
    assert "orchestration.cycle_complete" in events


def test_cycle_count_tracking(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    async def _run():
        ooda.set_goal("test goal")
        assert ooda.cycle_count == 0
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        assert ooda.cycle_count == 1

    asyncio.run(_run())


def test_run_cycle_returns_none_when_no_action(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    async def _run():
        # No goal, no pending tasks -- nothing to do
        result = await ooda.run_cycle(chat_history=[])
        assert result is None

    asyncio.run(_run())
