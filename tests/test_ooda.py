"""Tests for the OODA loop orchestration engine."""
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
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "stub"})


def _make_ooda(tmp_path, mode=AutonomyMode.PLAN):
    bus = EventBus()
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(
        bus=bus,
        playbook=playbook,
        trust=TrustManager(),
        autonomy=AutonomyManager(initial_mode=mode),
        dispatcher=dispatcher,
        config={},
    )
    return bus, playbook, ooda


def test_ooda_initial_phase(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)
    assert ooda.phase == OODAPhase.SLEEP


def test_ooda_observe_returns_state(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        state = await ooda.observe()
        assert "pending_tasks" in state
        assert "recent_events" in state
        assert "playbook_recent" in state

    asyncio.run(_run())


def test_ooda_orient_with_goal(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        state = await ooda.observe()
        orientation = await ooda.orient(state, goal="Find profitable momentum strategies")
        assert "goal" in orientation
        assert "actions_needed" in orientation

    asyncio.run(_run())


def test_ooda_decide_returns_plan(tmp_path):
    """decide() must return a Plan object (uses fallback since no LLM configured)."""
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        ooda.set_goal("Find momentum strategies")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "momentum"}})
        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)
        assert plan is not None
        assert hasattr(plan, "steps")  # It's a Plan object
        assert hasattr(plan, "id")
        assert len(plan.steps) > 0

    asyncio.run(_run())


def test_ooda_decide_autopilot_auto_approves(tmp_path):
    """In Autopilot mode, decide() auto-approves all steps."""
    _, _, ooda = _make_ooda(tmp_path, mode=AutonomyMode.AUTOPILOT)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)
        assert plan is not None
        from quantclaw.execution.plan import StepStatus
        assert all(s.status == StepStatus.APPROVED for s in plan.steps)

    asyncio.run(_run())


def test_ooda_act_executes_plan(tmp_path):
    """act() executes the DAG via Dispatcher."""
    bus, _, ooda = _make_ooda(tmp_path, mode=AutonomyMode.AUTOPILOT)

    async def _run():
        from quantclaw.execution.plan import Plan, PlanStep, StepStatus
        plan = Plan(
            id="test-act",
            description="test",
            steps=[
                PlanStep(id=0, agent="researcher", task={"query": "test"},
                         description="test step", depends_on=[], status=StepStatus.APPROVED),
            ],
        )
        results = await ooda.act(plan)
        assert ooda.phase == OODAPhase.ACT
        assert isinstance(results, dict)
        assert 0 in results
        assert results[0].status == AgentStatus.SUCCESS

    asyncio.run(_run())


def test_ooda_learn_adds_to_playbook(tmp_path):
    _, playbook, ooda = _make_ooda(tmp_path)

    async def _run():
        await ooda.learn({
            "type": "strategy_result",
            "content": {"strategy": "momentum_5d", "sharpe": 1.5},
            "tags": ["momentum"],
        })
        entries = await playbook.query(tags=["momentum"])
        assert len(entries) == 1

    asyncio.run(_run())


def test_ooda_phase_transitions(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        assert ooda.phase == OODAPhase.SLEEP

        await ooda.observe()
        assert ooda.phase == OODAPhase.OBSERVE

        state = await ooda.observe()
        await ooda.orient(state, goal="test")
        assert ooda.phase == OODAPhase.ORIENT

    asyncio.run(_run())


def test_ooda_sleep_wakes_on_event(tmp_path):
    """sleep_until_trigger() wakes when an event arrives on the bus."""
    bus, _, ooda = _make_ooda(tmp_path)

    async def _run():
        wake_task = asyncio.create_task(ooda.sleep_until_trigger(timeout=5.0))
        await asyncio.sleep(0.05)
        await bus.publish(Event(
            type=EventType.AGENT_TASK_COMPLETED,
            payload={"agent": "researcher"},
            source_agent="researcher",
        ))
        await asyncio.wait_for(wake_task, timeout=1.0)
        assert ooda.phase == OODAPhase.OBSERVE  # Woke up

    asyncio.run(_run())
