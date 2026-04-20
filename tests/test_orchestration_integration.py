"""Integration test: full OODA cycle with all orchestration components."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook, EntryType
from quantclaw.orchestration.trust import TrustManager, TrustLevel, RiskGuardrails
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool
from quantclaw.execution.plan import Plan, PlanStep, StepStatus


class MockResearcher(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "findings": "Momentum factor shows promise in current regime"
        })


class MockValidator(BaseAgent):
    name = "validator"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        upstream = task.get("_upstream_results", {})
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "sharpe": 1.5, "annual_return": 0.18, "max_drawdown": -0.08
        })


@pytest.fixture
def setup(tmp_path):
    bus = EventBus()
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    trust = TrustManager()
    autonomy = AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT)
    config = {"risk": {"max_drawdown": -0.10, "max_position_pct": 0.05}}
    pool = AgentPool(bus=bus, config=config)
    pool.register("researcher", MockResearcher)
    pool.register("validator", MockValidator)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(bus=bus, playbook=playbook, trust=trust, autonomy=autonomy,
                    dispatcher=dispatcher, config=config)
    return bus, playbook, trust, autonomy, dispatcher, ooda


def test_full_ooda_cycle(setup):
    bus, playbook, trust, autonomy, dispatcher, ooda = setup

    async def _run():
        # 1. Set goal
        ooda.set_goal("Find profitable momentum strategies")

        # 2. OBSERVE
        state = await ooda.observe()
        assert ooda.phase == OODAPhase.OBSERVE

        # 3. ORIENT
        orientation = await ooda.orient(state)
        assert ooda.phase == OODAPhase.ORIENT
        assert "plan_toward_goal" in orientation["actions_needed"]

        # 4. DECIDE — returns a Plan object via Planner (with fallback)
        plan = await ooda.decide(orientation)
        assert ooda.phase == OODAPhase.DECIDE
        assert plan is not None
        assert hasattr(plan, "steps")

        # 5. ACT — uses ooda.act() to execute via Dispatcher
        # For this test, create a known plan instead of LLM-generated one
        exec_plan = Plan(
            id="momentum-search",
            description="Search for momentum strategies",
            steps=[
                PlanStep(id=0, agent="researcher", task={"query": "momentum factors"},
                         description="Research momentum", depends_on=[], status=StepStatus.APPROVED),
                PlanStep(id=1, agent="validator", task={"strategy": "momentum_5d"},
                         description="Backtest momentum", depends_on=[0], status=StepStatus.APPROVED),
            ],
        )
        results = await ooda.act(exec_plan)
        assert ooda.phase == OODAPhase.ACT
        assert results[0].status == AgentStatus.SUCCESS
        assert results[1].status == AgentStatus.SUCCESS
        assert results[1].data["sharpe"] == 1.5

        # 6. LEARN
        await ooda.learn({
            "type": "strategy_result",
            "content": {
                "strategy": "momentum_5d",
                "sharpe": results[1].data["sharpe"],
                "annual_return": results[1].data["annual_return"],
            },
            "tags": ["momentum", "backtest"],
        })

        entries = await playbook.query(tags=["momentum"])
        assert len(entries) == 1
        assert entries[0].content["sharpe"] == 1.5

        # 7. SLEEP
        await ooda.sleep()
        assert ooda.phase == OODAPhase.SLEEP

    asyncio.run(_run())


def test_plan_mode_requires_approval(setup):
    bus, playbook, trust, autonomy, dispatcher, ooda = setup

    async def _run():
        autonomy.set_mode(AutonomyMode.PLAN)
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})

        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)

        assert plan is not None
        # Plan Mode: steps should NOT be auto-approved
        assert all(s.status == StepStatus.PENDING for s in plan.steps)

    asyncio.run(_run())


def test_risk_guardrails_enforced(setup):
    bus, playbook, trust, autonomy, dispatcher, ooda = setup

    guardrails = RiskGuardrails.from_config({"risk": {"max_drawdown": -0.10, "max_position_pct": 0.05}})

    # Position too large
    assert not guardrails.check_position_size(0.10, 100000)

    # Drawdown exceeded
    assert not guardrails.check_drawdown(-0.12)

    # Trust level blocks live trading at Observer
    assert not trust.can_live_trade()
    asyncio.run(trust.upgrade(TrustLevel.PAPER_TRADER))
    assert not trust.can_live_trade()
    assert trust.can_paper_trade()
