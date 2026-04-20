"""Integration test: full orchestration activation flow."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool


class MockResearcher(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "findings": "Momentum factor looks promising"
        })


def test_chat_to_ooda_to_results(tmp_path):
    """Simulate: CEO sends message -> OODA cycle -> agents execute -> results."""
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", MockResearcher)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT),
                    dispatcher=dispatcher, config={})

    cycle_completed = []

    async def capture_cycle(event):
        if str(event.type) == "orchestration.cycle_complete":
            cycle_completed.append(True)

    bus.subscribe("orchestration.*", capture_cycle)

    async def _run():
        ooda.set_goal("find momentum strategies")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "momentum"}})

        results = await ooda.run_cycle(chat_history=[
            {"role": "user", "content": "find momentum strategies"}
        ])

        # Give event handlers time to fire (they use create_task)
        await asyncio.sleep(0.1)

        assert results is not None
        assert ooda.phase == OODAPhase.SLEEP
        assert ooda.cycle_count == 1
        assert len(cycle_completed) >= 1

    asyncio.run(_run())


def test_cancel_and_replace(tmp_path):
    """Simulate: CEO sends message, then cancels mid-cycle."""
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})

    class SlowAgent(BaseAgent):
        name = "researcher"
        model = "sonnet"
        async def execute(self, task: dict) -> AgentResult:
            await asyncio.sleep(2)
            return AgentResult(status=AgentStatus.SUCCESS, data={"slow": True})

    pool.register("researcher", SlowAgent)
    cancel = asyncio.Event()
    dispatcher = Dispatcher(pool=pool, bus=bus, cancel_event=cancel)
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT),
                    dispatcher=dispatcher, config={})

    async def _run():
        ooda.set_goal("first task")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "slow"}})

        cycle_task = asyncio.create_task(ooda.run_cycle())

        await asyncio.sleep(0.1)
        cancel.set()
        await asyncio.sleep(0.1)

        try:
            await asyncio.wait_for(cycle_task, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        cancel.clear()

    asyncio.run(_run())


def test_state_persists_across_restart(tmp_path):
    """Simulate: set goal + mode, then restore from playbook."""
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        # Session 1: set state
        bus1 = EventBus()
        pool1 = AgentPool(bus=bus1, config={})
        dispatcher1 = Dispatcher(pool=pool1, bus=bus1)
        autonomy1 = AutonomyManager(playbook=pb)
        ooda1 = OODALoop(bus=bus1, playbook=pb, trust=TrustManager(),
                         autonomy=autonomy1, dispatcher=dispatcher1, config={})

        await ooda1.set_goal_persistent("find alpha")
        await autonomy1.set_mode_persistent(AutonomyMode.AUTOPILOT)

        # Session 2: restore
        autonomy2 = await AutonomyManager.from_playbook(pb)
        goal = await OODALoop.restore_goal(pb)

        assert autonomy2.mode == AutonomyMode.AUTOPILOT
        assert goal == "find alpha"

    asyncio.run(_run())
