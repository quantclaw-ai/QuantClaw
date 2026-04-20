"""Tests for persistent profit campaigns above the OODA loop."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.campaigns import CampaignManager, CampaignPhase, CampaignStatus
from quantclaw.orchestration.deployments import DeploymentAllocator, DeploymentStatus
from quantclaw.orchestration.ooda import OODALoop
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool


def test_campaign_manager_matches_and_generates_subgoal(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={})

    campaign = manager.activate("go make me cash")

    assert campaign is not None
    assert campaign.phase == CampaignPhase.DISCOVER

    subgoal = manager.next_subgoal(campaign)
    assert "Campaign objective: go make me cash." in subgoal
    assert "paper" in subgoal.lower()


def test_campaign_manager_promotes_through_validate_and_paper(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {
            "min_discovery_cycles": 2,
            "discovery_promote_sharpe": 0.75,
            "validation_promote_held_out_sharpe": 0.25,
        },
    })
    campaign = manager.activate("go make me cash")
    assert campaign is not None

    campaign.phase_cycles = 2
    campaign.best_sharpe = 0.9
    manager.next_subgoal(campaign)
    assert campaign.phase == CampaignPhase.VALIDATE

    async def _run():
        update = await manager.record_cycle(
            campaign,
            {
                0: AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"held_out_sharpe": 0.5, "verdict": "validated"},
                ),
            },
            {"verdict": "pursue", "reasoning": "validated out-of-sample"},
        )
        assert campaign.phase == CampaignPhase.PAPER
        assert "validate -> paper" in update.transition_message

    asyncio.run(_run())


def test_paper_phase_does_not_pause_on_flat_sharpe(tmp_path):
    """Reproduces a real production pause: campaign in PAPER, six cycles
    with the same best_sharpe (because paper is steady-state operation
    of an existing strategy), pre-fix this triggered max_stagnant_cycles=6
    and paused the campaign with stop_reason='No material improvement
    for 6 cycles'. After the fix, paper phase ignores stagnation entirely.
    """
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {
            "max_total_cycles": 0,           # unlimited
            "max_stagnant_cycles": 6,
            "max_refine_cycles": 10,
        },
    })
    campaign = manager.activate("go make me cash")
    assert campaign is not None
    campaign.phase = CampaignPhase.PAPER
    campaign.best_sharpe = 0.85
    campaign.best_held_out_sharpe = 0.75

    async def _run():
        # Six paper cycles where Sharpe stays flat (the expected behavior
        # of paper trading — you're running, not searching).
        for _ in range(6):
            await manager.record_cycle(
                campaign,
                {0: AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"sharpe": 0.85, "held_out_sharpe": 0.75,
                          "mode": "paper", "max_drawdown": -0.02},
                )},
                {"verdict": "iterate", "reasoning": "running"},
            )
        assert campaign.status == CampaignStatus.ACTIVE, (
            f"Paper phase should ignore stagnation. Got stop_reason={campaign.stop_reason!r}"
        )

    asyncio.run(_run())


def test_paper_phase_pauses_on_drawdown_breach(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {"max_total_cycles": 0, "max_stagnant_cycles": 100,
                      "max_refine_cycles": 10},
        "risk": {"max_drawdown": -0.10},
    })
    campaign = manager.activate("go make me cash")
    campaign.phase = CampaignPhase.PAPER

    async def _run():
        update = await manager.record_cycle(
            campaign,
            {0: AgentResult(
                status=AgentStatus.SUCCESS,
                data={"sharpe": 0.5, "mode": "paper", "max_drawdown": -0.12},
            )},
            {"verdict": "iterate", "reasoning": "drawdown rising"},
        )
        assert campaign.status == CampaignStatus.PAUSED
        assert "drawdown" in campaign.stop_reason.lower()
        assert update.status_message != ""

    asyncio.run(_run())


def test_paper_phase_pauses_on_consecutive_non_execute(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {
            "max_total_cycles": 0,
            "max_stagnant_cycles": 100,
            "max_refine_cycles": 10,
            "max_consecutive_paper_failures": 3,
        },
    })
    campaign = manager.activate("go make me cash")
    campaign.phase = CampaignPhase.PAPER

    async def _run():
        for _ in range(3):
            await manager.record_cycle(
                campaign,
                {0: AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"sharpe": 0.5, "mode": "backtest"},  # NOT paper
                )},
                {"verdict": "iterate", "reasoning": "no orders"},
            )
        assert campaign.status == CampaignStatus.PAUSED
        assert "execut" in campaign.stop_reason.lower() or "paper" in campaign.stop_reason.lower()

    asyncio.run(_run())


def test_paper_recovers_consecutive_counter_on_successful_execute(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {"max_total_cycles": 0, "max_stagnant_cycles": 100,
                      "max_refine_cycles": 10,
                      "max_consecutive_paper_failures": 3},
    })
    campaign = manager.activate("go make me cash")
    campaign.phase = CampaignPhase.PAPER

    async def _run():
        # Two non-execute cycles, then one successful — counter should reset.
        for _ in range(2):
            await manager.record_cycle(
                campaign,
                {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.5})},
                {"verdict": "iterate"},
            )
        await manager.record_cycle(
            campaign,
            {0: AgentResult(
                status=AgentStatus.SUCCESS,
                data={"sharpe": 0.5, "mode": "paper", "max_drawdown": -0.01},
            )},
            {"verdict": "iterate"},
        )
        # Two more non-executes shouldn't yet pause (counter reset).
        for _ in range(2):
            await manager.record_cycle(
                campaign,
                {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.5})},
                {"verdict": "iterate"},
            )
        assert campaign.status == CampaignStatus.ACTIVE

    asyncio.run(_run())


def test_phase_transition_resets_improvement_clock(tmp_path):
    """Entering paper from validate should not carry over stagnation counted
    in earlier search phases."""
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {
            "max_total_cycles": 0,
            "max_stagnant_cycles": 4,
            "discovery_promote_sharpe": 0.5,
            "min_discovery_cycles": 0,
        },
    })
    campaign = manager.activate("go make me cash")

    async def _run():
        # Two discovery cycles getting up to 0.6 Sharpe; promotes to validate.
        await manager.record_cycle(
            campaign,
            {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.6})},
            {"verdict": "pursue"},
        )
        # Next cycle: validated -> jumps to PAPER, clock should reset.
        await manager.record_cycle(
            campaign,
            {0: AgentResult(
                status=AgentStatus.SUCCESS,
                data={"sharpe": 0.7, "held_out_sharpe": 0.4,
                      "verdict": "validated", "mode": "paper",
                      "max_drawdown": -0.01},
            )},
            {"verdict": "pursue"},
        )
        assert campaign.phase == CampaignPhase.PAPER
        # last_improvement_cycle should equal total_cycles right after transition.
        assert campaign.last_improvement_cycle == campaign.total_cycles

    asyncio.run(_run())


def test_campaign_manager_pauses_after_max_total_cycles(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {
            "max_total_cycles": 2,
            "max_stagnant_cycles": 10,
            "max_refine_cycles": 10,
        },
    })
    campaign = manager.activate("go make me cash")
    assert campaign is not None

    async def _run():
        await manager.record_cycle(
            campaign,
            {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.4})},
            {"verdict": "iterate", "reasoning": "still exploring"},
        )
        update = await manager.record_cycle(
            campaign,
            {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.45})},
            {"verdict": "iterate", "reasoning": "still exploring"},
        )
        assert campaign.status == CampaignStatus.PAUSED
        assert "paused after 2 cycles" in update.status_message

    asyncio.run(_run())


def test_campaign_manager_resume_resets_cycle_budget(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    manager = CampaignManager(playbook, config={
        "campaigns": {
            "max_total_cycles": 2,
            "max_stagnant_cycles": 10,
            "max_refine_cycles": 10,
        },
    })
    campaign = manager.activate("go make me cash")
    assert campaign is not None

    async def _run():
        await manager.record_cycle(
            campaign,
            {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.4})},
            {"verdict": "iterate", "reasoning": "still exploring"},
        )
        await manager.record_cycle(
            campaign,
            {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.45})},
            {"verdict": "iterate", "reasoning": "still exploring"},
        )
        assert campaign.status == CampaignStatus.PAUSED

        resumed = manager.activate("go make me cash", existing=campaign)
        assert resumed is campaign
        assert campaign.status == CampaignStatus.ACTIVE
        assert campaign.resume_cycle == 2

        update = await manager.record_cycle(
            campaign,
            {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.5})},
            {"verdict": "iterate", "reasoning": "resumed"},
        )
        assert campaign.status == CampaignStatus.ACTIVE
        assert update.status_message == ""

    asyncio.run(_run())


class StubAgent(BaseAgent):
    name = "researcher"
    model = "sonnet"

    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.8})


def _make_ooda(tmp_path):
    bus = EventBus()
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(
        bus=bus,
        playbook=playbook,
        trust=TrustManager(),
        autonomy=AutonomyManager(initial_mode=AutonomyMode.PLAN, playbook=playbook),
        dispatcher=dispatcher,
        config={"campaigns": {"auto_activate_autopilot": True}},
    )
    return playbook, ooda


def test_ooda_profit_goal_starts_campaign_and_autopilot(tmp_path):
    _, ooda = _make_ooda(tmp_path)

    async def _run():
        await ooda.set_goal_persistent("go make me cash")
        assert ooda.campaign is not None
        assert ooda.campaign.phase == CampaignPhase.DISCOVER
        assert ooda._autonomy.mode == AutonomyMode.AUTOPILOT

        state = await ooda.observe()
        orientation = await ooda.orient(state)
        assert orientation["goal"].startswith("Campaign objective:")

    asyncio.run(_run())


def test_ooda_restore_persistent_state_restores_campaign(tmp_path):
    playbook, ooda1 = _make_ooda(tmp_path)

    async def _setup():
        await ooda1.set_goal_persistent("go make me cash")

    asyncio.run(_setup())

    _, ooda2 = _make_ooda(tmp_path)

    async def _restore():
        await ooda2.restore_persistent_state()
        assert ooda2.campaign is not None
        assert ooda2.campaign.root_goal == "go make me cash"

    asyncio.run(_restore())


def test_deployment_allocator_ranks_active_and_watchlist(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    allocator = DeploymentAllocator(playbook, config={
        "campaigns": {
            "max_active_paper_deployments": 2,
            "paper_watchlist_size": 2,
            "validation_promote_held_out_sharpe": 0.25,
            "paper_candidate_min_sharpe": 1.0,
        },
    })

    async def _run():
        campaign_id = "camp-1"
        await allocator.rebalance(
            campaign_id,
            1,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/a.py",
                    "model_type": "ridge",
                    "sharpe": 1.3,
                    "annual_return": 0.12,
                    "max_drawdown": -0.08,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.35,
                    "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )
        await allocator.rebalance(
            campaign_id,
            2,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/b.py",
                    "model_type": "gradient_boosting",
                    "sharpe": 1.8,
                    "annual_return": 0.18,
                    "max_drawdown": -0.09,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.5,
                    "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )
        await allocator.rebalance(
            campaign_id,
            3,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/c.py",
                    "model_type": "linear",
                    "sharpe": 1.05,
                    "annual_return": 0.07,
                    "max_drawdown": -0.06,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.22,
                    "verdict": "pursue",
                }),
            },
            {"verdict": "pursue"},
        )

        deployments = await allocator.restore(campaign_id)
        active = [d for d in deployments if d.status == DeploymentStatus.ACTIVE]
        watchlist = [d for d in deployments if d.status == DeploymentStatus.WATCHLIST]

        assert len(active) == 2
        assert len(watchlist) >= 1
        assert sum(d.allocation_pct for d in active) == pytest.approx(1.0)
        assert any(d.strategy_path == "strategies/b.py" for d in active)

    asyncio.run(_run())


def test_ooda_observe_includes_deployment_context(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    allocator = DeploymentAllocator(playbook, config={
        "campaigns": {"max_active_paper_deployments": 1, "paper_watchlist_size": 1},
    })
    campaign = CampaignManager(playbook, config={}).activate("go make me cash")
    assert campaign is not None

    async def _seed():
        await allocator.rebalance(
            campaign.id,
            1,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/live_a.py",
                    "model_type": "ridge",
                    "sharpe": 1.4,
                    "annual_return": 0.13,
                    "max_drawdown": -0.07,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.4,
                    "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )

    asyncio.run(_seed())

    _, ooda = _make_ooda(tmp_path)
    ooda._campaign = campaign

    async def _run():
        state = await ooda.observe()
        assert state["deployments"]["active_count"] == 1

        orientation = await ooda.orient(state)
        assert orientation["deployment_context"]["active_count"] == 1
        assert "Current paper portfolio" in orientation["goal"]

    asyncio.run(_run())


def test_ooda_paper_phase_builds_deployment_runner_plan(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    allocator = DeploymentAllocator(playbook, config={
        "campaigns": {"max_active_paper_deployments": 1, "paper_watchlist_size": 1},
    })
    campaign = CampaignManager(playbook, config={}).activate("go make me cash")
    assert campaign is not None
    campaign.phase = CampaignPhase.PAPER

    async def _seed():
        await allocator.rebalance(
            campaign.id,
            1,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/paper_alpha.py",
                    "model_type": "ridge",
                    "sharpe": 1.4,
                    "annual_return": 0.15,
                    "max_drawdown": -0.08,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.45,
                    "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )

    asyncio.run(_seed())

    _, ooda = _make_ooda(tmp_path)
    ooda._campaign = campaign
    ooda._autonomy.set_mode(AutonomyMode.AUTOPILOT)

    async def _run():
        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)
        assert plan is not None
        assert plan.steps[0].agent == "executor"
        assert plan.steps[0].task["task"] == "run_deployments"
        assert plan.steps[1].agent == "reporter"

    asyncio.run(_run())


def test_paper_plan_skips_shadow_on_early_cycles(tmp_path):
    """First two paper cycles run executor + reporter only (cheap)."""
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    allocator = DeploymentAllocator(playbook, config={
        "campaigns": {"max_active_paper_deployments": 1, "paper_watchlist_size": 1},
    })
    campaign = CampaignManager(playbook, config={}).activate("go make me cash")
    assert campaign is not None
    campaign.phase = CampaignPhase.PAPER
    campaign.phase_cycles = 0  # first paper cycle being planned

    async def _seed():
        await allocator.rebalance(
            campaign.id, 1,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/incumbent.py", "model_type": "ridge",
                    "sharpe": 1.4, "annual_return": 0.15, "max_drawdown": -0.08,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.45, "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )
    asyncio.run(_seed())

    _, ooda = _make_ooda(tmp_path)
    ooda._campaign = campaign
    ooda._autonomy.set_mode(AutonomyMode.AUTOPILOT)

    async def _run():
        plan = await ooda.decide(await ooda.orient(await ooda.observe()))
        agents = [s.agent for s in plan.steps]
        assert agents == ["executor", "reporter"], (
            f"First paper cycle should be executor + reporter only, got {agents}"
        )

    asyncio.run(_run())


def test_paper_plan_runs_shadow_search_on_nth_cycle(tmp_path):
    """Every Nth paper cycle should also run a full discovery pipeline."""
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    allocator = DeploymentAllocator(playbook, config={
        "campaigns": {"max_active_paper_deployments": 1, "paper_watchlist_size": 1},
    })
    campaign = CampaignManager(playbook, config={}).activate("go make me cash")
    assert campaign is not None
    campaign.phase = CampaignPhase.PAPER
    # phase_cycles=2 means cycle being planned is the 3rd paper cycle.
    campaign.phase_cycles = 2

    async def _seed():
        await allocator.rebalance(
            campaign.id, 1,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/incumbent.py", "model_type": "ridge",
                    "sharpe": 1.4, "annual_return": 0.15, "max_drawdown": -0.08,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.45, "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )
    asyncio.run(_seed())

    _, ooda = _make_ooda(tmp_path)
    ooda._campaign = campaign
    ooda._autonomy.set_mode(AutonomyMode.AUTOPILOT)
    ooda._config.setdefault("campaigns", {})["paper_shadow_search_every"] = 3

    async def _run():
        plan = await ooda.decide(await ooda.orient(await ooda.observe()))
        agents = [s.agent for s in plan.steps]
        # Paper executor first, then full discovery pipeline, then a unified reporter.
        assert agents[0] == "executor"
        assert "miner" in agents
        assert "trainer" in agents
        assert "validator" in agents
        assert agents[-1] == "reporter"
        # Reporter must depend on both the paper run AND the search pipeline tail.
        reporter_step = plan.steps[-1]
        assert 0 in reporter_step.depends_on
        assert any(d > 0 for d in reporter_step.depends_on)
        # All search steps tagged shadow.
        for s in plan.steps[1:-1]:
            assert s.task.get("shadow") is True

    asyncio.run(_run())


def test_paper_plan_shadow_search_disabled_with_zero(tmp_path):
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    allocator = DeploymentAllocator(playbook, config={
        "campaigns": {"max_active_paper_deployments": 1, "paper_watchlist_size": 1},
    })
    campaign = CampaignManager(playbook, config={}).activate("go make me cash")
    campaign.phase = CampaignPhase.PAPER
    campaign.phase_cycles = 99  # would normally trigger shadow

    async def _seed():
        await allocator.rebalance(
            campaign.id, 1,
            {
                0: AgentResult(status=AgentStatus.SUCCESS, data={
                    "strategy_path": "strategies/incumbent.py", "model_type": "ridge",
                    "sharpe": 1.4, "annual_return": 0.15, "max_drawdown": -0.08,
                }),
                1: AgentResult(status=AgentStatus.SUCCESS, data={
                    "held_out_sharpe": 0.45, "verdict": "validated",
                }),
            },
            {"verdict": "pursue"},
        )
    asyncio.run(_seed())

    _, ooda = _make_ooda(tmp_path)
    ooda._campaign = campaign
    ooda._autonomy.set_mode(AutonomyMode.AUTOPILOT)
    ooda._config.setdefault("campaigns", {})["paper_shadow_search_every"] = 0

    async def _run():
        plan = await ooda.decide(await ooda.orient(await ooda.observe()))
        assert [s.agent for s in plan.steps] == ["executor", "reporter"]

    asyncio.run(_run())


def test_ooda_summary_merges_backtest_and_held_out_results():
    summary = OODALoop._summarize_cycle_results({
        0: AgentResult(status=AgentStatus.SUCCESS, data={
            "sharpe": 2.27,
            "annual_return": 0.54,
            "max_drawdown": -0.17,
            "total_trades": 586,
        }),
        1: AgentResult(status=AgentStatus.SUCCESS, data={
            "verdict": "validated",
            "reason": "Held-out Sharpe 4.32 (190% of in-sample 2.27)",
            "held_out_sharpe": 4.32,
            "held_out_trades": 61,
            "degradation_ratio": 1.9,
            "in_sample_sharpe": 2.27,
        }),
    })
    best = summary["best_result"]
    assert best["sharpe"] == pytest.approx(2.27)
    assert best["held_out_sharpe"] == pytest.approx(4.32)
    assert best["verdict"] == "validated"


def test_ooda_evaluate_results_handles_paper_cycles(tmp_path):
    _, ooda = _make_ooda(tmp_path)

    async def _run():
        evaluation = await ooda._evaluate_results({
            0: AgentResult(status=AgentStatus.SUCCESS, data={
                "mode": "paper",
                "paper_mode": True,
                "orders_executed": 2,
                "deployment_updates": [
                    {"status": "ok", "deployment_id": "dep-1"},
                    {"status": "ok", "deployment_id": "dep-2"},
                ],
            }),
        }, iteration=1)
        assert evaluation["verdict"] == "pursue"
        assert "Paper portfolio rebalanced" in evaluation["reasoning"]

    asyncio.run(_run())
