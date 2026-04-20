"""E2E test: validates data shape contracts between agents in the pipeline."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool
from quantclaw.execution.plan import Plan, PlanStep, StepStatus


class MockIngestor(BaseAgent):
    name = "ingestor"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "ohlcv": {
                "AAPL": {"rows": 252, "start": "2023-01-03", "end": "2023-12-29", "last_close": 155.0},
                "MSFT": {"rows": 252, "start": "2023-01-03", "end": "2023-12-29", "last_close": 380.0},
            },
        })


class MockMiner(BaseAgent):
    name = "miner"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        # Should receive Ingestor data via _upstream_results
        upstream = task.get("_upstream_results", {})
        has_upstream = len(upstream) > 0
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "factors": [
                {"name": "momentum_5d", "code": "df['close'].pct_change(5)",
                 "hypothesis": "5-day momentum", "data_types": ["price"],
                 "metrics": {"ic": 0.05, "rank_ic": 0.08, "sharpe": 1.2, "turnover": 0.3},
                 "lineage": {"parent": None, "generation": 0, "method": "exploration"}},
            ],
            "generations_run": 1,
            "best_sharpe": 1.2,
            "best_ic": 0.05,
            "received_upstream": has_upstream,
        })


class MockTrainer(BaseAgent):
    name = "trainer"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        # Should receive Miner factors via _upstream_results
        upstream = task.get("_upstream_results", {})
        factors = task.get("factors", [])
        # Extract from upstream if not provided directly
        if not factors:
            for data in upstream.values():
                if isinstance(data, dict) and "factors" in data:
                    factors = data["factors"]
                    break

        return AgentResult(status=AgentStatus.SUCCESS, data={
            "model_type": "gradient_boosting",
            "model_id": "gbm_test123",
            "model_path": "data/models/gbm_test123.pkl",
            "strategy_path": "data/strategies/gbm_test123.py",
            "features_used": [f["name"] for f in factors],
            "feature_importance": {f["name"]: 0.5 for f in factors},
            "metrics": {"train_sharpe": 1.8, "test_sharpe": 1.1, "accuracy": 0.54, "overfit_ratio": 1.64},
            "strategy_code": "class Strategy: pass",
            "sharpe": 1.1,
            "received_factors_count": len(factors),
        })


class MockValidator(BaseAgent):
    name = "validator"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        upstream = task.get("_upstream_results", {})
        has_strategy = any(
            isinstance(v, dict) and "strategy_code" in v
            for v in upstream.values()
        )
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "sharpe": 1.4,
            "annual_return": 0.22,
            "max_drawdown": -0.08,
            "total_trades": 48,
            "win_rate": 0.58,
            "received_strategy": has_strategy,
        })


def test_full_pipeline_data_flow():
    """Test that data flows correctly: Ingestor -> Miner -> Trainer -> Backtester."""
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("ingestor", MockIngestor)
    pool.register("miner", MockMiner)
    pool.register("trainer", MockTrainer)
    pool.register("validator", MockValidator)
    dispatcher = Dispatcher(pool=pool, bus=bus)

    plan = Plan(
        id="e2e-test",
        description="full pipeline",
        steps=[
            PlanStep(id=0, agent="ingestor", task={"symbols": ["AAPL", "MSFT"]},
                     description="fetch data", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="miner", task={"goal": "find alpha"},
                     description="discover factors", depends_on=[0], status=StepStatus.APPROVED),
            PlanStep(id=2, agent="trainer", task={"model_type": "gradient_boosting"},
                     description="train model", depends_on=[1], status=StepStatus.APPROVED),
            PlanStep(id=3, agent="validator", task={"strategy": "test"},
                     description="evaluate", depends_on=[2], status=StepStatus.APPROVED),
        ],
    )

    results = asyncio.run(dispatcher.execute_plan(plan))

    # All steps succeeded
    assert all(r.status == AgentStatus.SUCCESS for r in results.values())

    # Verify data flowed downstream
    assert results[1].data["received_upstream"] is True  # Miner got Ingestor data
    assert results[2].data["received_factors_count"] == 1  # Trainer got 1 factor from Miner
    assert results[3].data["received_strategy"] is True  # Backtester got strategy from Trainer


def test_pipeline_handles_step_failure():
    """If a middle step fails, downstream steps are blocked (deps not met)."""
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})

    class FailingMiner(BaseAgent):
        name = "miner"
        model = "sonnet"
        async def execute(self, task: dict) -> AgentResult:
            return AgentResult(status=AgentStatus.FAILED, error="Mining failed")

    pool.register("ingestor", MockIngestor)
    pool.register("miner", FailingMiner)
    pool.register("trainer", MockTrainer)
    pool.register("validator", MockValidator)
    dispatcher = Dispatcher(pool=pool, bus=bus)

    plan = Plan(
        id="fail-test",
        description="pipeline with failure",
        steps=[
            PlanStep(id=0, agent="ingestor", task={},
                     description="fetch", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="miner", task={},
                     description="mine", depends_on=[0], status=StepStatus.APPROVED),
            PlanStep(id=2, agent="trainer", task={},
                     description="train", depends_on=[1], status=StepStatus.APPROVED),
        ],
    )

    results = asyncio.run(dispatcher.execute_plan(plan))

    assert results[0].status == AgentStatus.SUCCESS
    assert results[1].status == AgentStatus.FAILED
    # Step 2 never ran because its dependency (step 1) failed, not completed
    assert 2 not in results


def test_parallel_steps_both_feed_downstream():
    """Parallel steps (Researcher + Ingestor) both feed into Miner."""
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})

    class MockResearcher(BaseAgent):
        name = "researcher"
        model = "sonnet"
        async def execute(self, task: dict) -> AgentResult:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "findings": [{"topic": "momentum", "relevance": "high"}],
                "suggested_factors": ["momentum_5d"],
            })

    pool.register("researcher", MockResearcher)
    pool.register("ingestor", MockIngestor)
    pool.register("miner", MockMiner)
    dispatcher = Dispatcher(pool=pool, bus=bus)

    plan = Plan(
        id="parallel-test",
        description="parallel steps",
        steps=[
            PlanStep(id=0, agent="researcher", task={"topic": "alpha"},
                     description="research", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="ingestor", task={"symbols": ["AAPL"]},
                     description="fetch", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=2, agent="miner", task={"goal": "find alpha"},
                     description="mine", depends_on=[0, 1], status=StepStatus.APPROVED),
        ],
    )

    results = asyncio.run(dispatcher.execute_plan(plan))

    assert all(r.status == AgentStatus.SUCCESS for r in results.values())
    # Miner should have received upstream from both researcher (0) and ingestor (1)
    assert results[2].data["received_upstream"] is True
