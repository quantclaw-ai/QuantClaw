"""Tests for Scheduler intelligence: exploration mode and result evaluation."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook, EntryType
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool


class StubAgent(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "stub", "sharpe": 0.5})


def _make(tmp_path, mode=AutonomyMode.AUTOPILOT):
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
                    autonomy=AutonomyManager(initial_mode=mode),
                    dispatcher=dispatcher, config=config)
    return bus, pb, ooda


def test_exploration_mode_empty_playbook(tmp_path):
    _, pb, ooda = _make(tmp_path)
    async def _run():
        mode, temp = await ooda._get_exploration_mode()
        assert mode == "explore"
        assert temp == 0.7
    asyncio.run(_run())


def test_exploration_mode_medium_playbook(tmp_path):
    _, pb, ooda = _make(tmp_path)
    async def _run():
        for i in range(10):
            await pb.add(EntryType.STRATEGY_RESULT, {"sharpe": i * 0.1}, tags=["test"])
        mode, temp = await ooda._get_exploration_mode()
        assert mode == "balanced"
        assert temp == 0.4
    asyncio.run(_run())


def test_exploration_mode_large_playbook(tmp_path):
    _, pb, ooda = _make(tmp_path)
    async def _run():
        for i in range(20):
            await pb.add(EntryType.STRATEGY_RESULT, {"sharpe": i * 0.1}, tags=["test"])
        mode, temp = await ooda._get_exploration_mode()
        assert mode == "exploit"
        assert temp == 0.2
    asyncio.run(_run())


def test_evaluate_results_no_history(tmp_path):
    _, pb, ooda = _make(tmp_path)
    async def _run():
        results = {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 1.0})}
        evaluation = await ooda._evaluate_results(results, iteration=1)
        assert evaluation["percentile"] is None
        assert "verdict" in evaluation
    asyncio.run(_run())


def test_evaluate_results_with_history(tmp_path):
    _, pb, ooda = _make(tmp_path)
    async def _run():
        for s in [0.2, 0.5, 0.8, 1.0, 1.2]:
            await pb.add(EntryType.STRATEGY_RESULT, {"sharpe": s}, tags=["test"])
        results = {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 1.5})}
        evaluation = await ooda._evaluate_results(results, iteration=1)
        assert evaluation["percentile"] is not None
        assert evaluation["percentile"] == 1.0
    asyncio.run(_run())


def test_iteration_context_accumulates(tmp_path):
    _, pb, ooda = _make(tmp_path)
    async def _run():
        assert len(ooda._iteration_context) == 0
        ooda._iteration_context.append({
            "iteration": 1,
            "results": {"sharpe": 0.3},
            "verdict": "iterate",
            "suggestion": "try volatility",
        })
        assert len(ooda._iteration_context) == 1
    asyncio.run(_run())
