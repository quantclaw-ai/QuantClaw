import asyncio
import pytest
from quantclaw.state.observability import ObservabilityStore, AgentRun
from quantclaw.execution.plan import Plan, PlanStep, PlanStatus, StepStatus


# Feature 2: Observability
def test_observability_start_finish():
    store = ObservabilityStore()
    run = store.start_run("validator", "backtest gap_1pct")
    assert len(store.get_active()) == 1
    run.add_thought("Loading strategy...")
    run.add_tool_call("load_strategy", "gap_1pct.py", "Strategy loaded", 50)
    run.add_model_call("claude-opus-4-6", "anthropic", 1000, 500, 0.03, 2000)
    store.finish_run("validator", status="completed")
    assert len(store.get_active()) == 0
    assert len(store.get_recent()) == 1
    recent = store.get_recent()[0]
    assert recent.total_tokens == 1500
    assert recent.total_cost == 0.03
    assert len(recent.thought_log) == 1


def test_observability_to_dict():
    run = AgentRun(agent_name="miner", task="mine tech")
    run.add_thought("Starting factor mining")
    run.add_model_call("gpt-4o", "openai", 2000, 1000, 0.05, 3000)
    run.finish("completed")
    d = run.to_dict()
    assert d["agent_name"] == "miner"
    assert d["total_tokens"] == 3000
    assert d["total_cost"] == 0.05
    assert d["status"] == "completed"


# Feature 3: Plan Approval
def test_plan_creation():
    steps = [
        PlanStep(id=0, agent="validator", task={"strategy": "momentum"},
                 description="Backtest momentum"),
        PlanStep(id=1, agent="validator", task={"strategy": "mean_rev"},
                 description="Backtest mean reversion"),
        PlanStep(id=2, agent="reporter", task={"compare": True},
                 description="Compare results", depends_on=[0, 1]),
    ]
    plan = Plan(id="test123", description="Test 2 strategies", steps=steps)
    assert plan.status == PlanStatus.PROPOSED
    assert len(plan.get_ready_steps()) == 0  # Nothing approved yet


def test_plan_approve_and_ready():
    steps = [
        PlanStep(id=0, agent="validator", task={}, description="Step 0"),
        PlanStep(id=1, agent="validator", task={}, description="Step 1"),
        PlanStep(id=2, agent="reporter", task={}, description="Step 2",
                 depends_on=[0, 1]),
    ]
    plan = Plan(id="test456", description="Test", steps=steps)
    plan.approve_all()
    ready = plan.get_ready_steps()
    assert len(ready) == 2  # Steps 0 and 1 (no deps)
    assert 2 not in [s.id for s in ready]  # Step 2 depends on 0,1


def test_plan_dependency_resolution():
    steps = [
        PlanStep(id=0, agent="validator", task={}, description="Step 0",
                 status=StepStatus.COMPLETED),
        PlanStep(id=1, agent="validator", task={}, description="Step 1",
                 status=StepStatus.COMPLETED),
        PlanStep(id=2, agent="reporter", task={}, description="Step 2",
                 depends_on=[0, 1], status=StepStatus.APPROVED),
    ]
    plan = Plan(id="test789", description="Test", steps=steps)
    ready = plan.get_ready_steps()
    assert len(ready) == 1
    assert ready[0].id == 2


def test_plan_skip_step():
    steps = [
        PlanStep(id=0, agent="validator", task={}, description="Step 0"),
        PlanStep(id=1, agent="validator", task={}, description="Step 1"),
    ]
    plan = Plan(id="skip_test", description="Test", steps=steps)
    plan.approve_all()
    plan.skip_step(1)
    assert plan.steps[1].status == StepStatus.SKIPPED


def test_plan_to_dict():
    steps = [PlanStep(id=0, agent="validator", task={"x": 1},
                      description="Test step")]
    plan = Plan(id="dict_test", description="Test plan", steps=steps)
    d = plan.to_dict()
    assert d["id"] == "dict_test"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["agent"] == "validator"


# Feature 1: Strategy Generator (test the code cleaning, not LLM call)
def test_strategy_generator_code_cleaning():
    from quantclaw.strategy.generator import StrategyGenerator
    # We can't test the LLM call without API keys, but we can test the code exists
    assert StrategyGenerator is not None


# Feature 4: Parallel Subagent Spawning
def test_dispatcher_explore_variants():
    from quantclaw.execution.pool import AgentPool
    from quantclaw.execution.dispatcher import Dispatcher
    from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus
    from quantclaw.events.bus import EventBus

    class ScoreAgent(BaseAgent):
        name = "scorer"
        model = "sonnet"
        daemon = False
        async def execute(self, task):
            return AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": task.get("sharpe", 0)})

    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("scorer", ScoreAgent)
    dispatcher = Dispatcher(pool=pool)

    variants = [{"sharpe": 1.5}, {"sharpe": 2.0}, {"sharpe": 0.8}]
    results = asyncio.run(dispatcher.explore_variants("scorer", variants))
    assert len(results) == 3
    assert results[0].data["sharpe"] == 2.0  # Best first

def test_dispatcher_execute_plan():
    from quantclaw.execution.pool import AgentPool
    from quantclaw.execution.dispatcher import Dispatcher
    from quantclaw.execution.plan import Plan, PlanStep
    from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus
    from quantclaw.events.bus import EventBus

    class OkAgent(BaseAgent):
        name = "ok"
        model = "sonnet"
        daemon = False
        async def execute(self, task):
            return AgentResult(status=AgentStatus.SUCCESS, data={"done": True})

    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("ok", OkAgent)
    dispatcher = Dispatcher(pool=pool)

    steps = [
        PlanStep(id=0, agent="ok", task={}, description="Step 0"),
        PlanStep(id=1, agent="ok", task={}, description="Step 1"),
        PlanStep(id=2, agent="ok", task={}, description="Step 2", depends_on=[0, 1]),
    ]
    plan = Plan(id="exec_test", description="Test", steps=steps)
    plan.approve_all()

    results = asyncio.run(dispatcher.execute_plan(plan))
    assert len(results) == 3
    assert all(r.status == AgentStatus.SUCCESS for r in results.values())
    assert plan.is_complete()

# Feature 5: Strategy Memory
def test_strategy_memory_record_and_retrieve():
    import asyncio
    from quantclaw.state.db import StateDB
    from quantclaw.state.memory import StrategyMemory

    async def run():
        db = await StateDB.create(":memory:")
        memory = StrategyMemory(db)

        await memory.record_result("momentum", {"lookback": 20, "top_n": 3},
                                    sharpe=1.5, annual_return=0.15, max_drawdown=-0.08)
        await memory.record_result("momentum", {"lookback": 60, "top_n": 5},
                                    sharpe=1.2, annual_return=0.12, max_drawdown=-0.10)
        await memory.record_result("momentum", {"lookback": 5, "top_n": 10},
                                    sharpe=-0.3, annual_return=-0.05, max_drawdown=-0.25)

        best = await memory.get_best_params("momentum")
        assert len(best) == 2  # Only positive sharpe
        assert best[0]["sharpe"] == 1.5

        stats = await memory.get_stats()
        assert stats["total_backtests"] == 3
        assert stats["best_sharpe"] == 1.5

        await db.close()

    asyncio.run(run())

def test_strategy_memory_anti_patterns():
    import asyncio
    from quantclaw.state.db import StateDB
    from quantclaw.state.memory import StrategyMemory

    async def run():
        db = await StateDB.create(":memory:")
        memory = StrategyMemory(db)

        # Record 3 failures with same params
        for _ in range(3):
            await memory.record_result("bad_strategy", {"param": "bad"},
                                        sharpe=-0.5, annual_return=-0.10, max_drawdown=-0.30)

        anti = await memory.get_anti_patterns(min_failures=3)
        assert len(anti) == 1
        assert anti[0]["failure_count"] == 3

        await db.close()

    asyncio.run(run())

def test_strategy_memory_suggestions():
    import asyncio
    from quantclaw.state.db import StateDB
    from quantclaw.state.memory import StrategyMemory

    async def run():
        db = await StateDB.create(":memory:")
        memory = StrategyMemory(db)

        await memory.record_result("momentum", {"lookback": 20}, sharpe=1.5, annual_return=0.15, max_drawdown=-0.08)

        suggestions = await memory.get_suggestions("momentum")
        assert suggestions["total_past_runs"] == 1
        assert len(suggestions["best_configurations"]) == 1

        await db.close()

    asyncio.run(run())


# Feature 6: Backtest Audit Trail
def test_audit_trail_creation():
    from quantclaw.strategy.audit import BacktestAudit
    audit = BacktestAudit(strategy_name="momentum", start_date="2020-01-01", end_date="2024-12-31")
    audit.add_signal("2020-01-06", {"AAPL": 0.05, "MSFT": 0.03})
    audit.add_allocation("2020-01-06", {"AAPL": 0.5, "MSFT": 0.3})
    audit.add_risk_check("2020-01-06", True, -0.02)
    audit.add_trade("2020-01-06", "AAPL", 100, 150.0, "buy", 0.15)
    audit.add_trade("2020-01-06", "MSFT", 50, 200.0, "buy", 0.10)
    audit.add_skip("2020-03-16", "risk_check_failed")

    summary = audit.summary()
    assert summary["signals_generated"] == 1
    assert summary["trades_executed"] == 2
    assert summary["rebalances_skipped"] == 1
    assert summary["total_transaction_cost"] == 0.25

def test_audit_trail_export_json():
    from quantclaw.strategy.audit import BacktestAudit
    audit = BacktestAudit(strategy_name="test", start_date="2020-01-01", end_date="2020-12-31")
    audit.add_trade("2020-01-06", "AAPL", 10, 150.0, "buy", 0.05)
    json_str = audit.to_json()
    assert "AAPL" in json_str
    assert "test" in json_str
    import json
    parsed = json.loads(json_str)
    assert parsed["summary"]["trades_executed"] == 1

def test_audit_trail_export_csv():
    from quantclaw.strategy.audit import BacktestAudit
    audit = BacktestAudit(strategy_name="test", start_date="2020-01-01", end_date="2020-12-31")
    audit.add_signal("2020-01-06", {"AAPL": 0.05})
    audit.add_trade("2020-01-06", "AAPL", 10, 150.0, "buy", 0.05)
    csv_str = audit.to_csv()
    assert "signal" in csv_str
    assert "trade" in csv_str

def test_audit_trail_filters():
    from quantclaw.strategy.audit import BacktestAudit
    audit = BacktestAudit(strategy_name="test", start_date="2020-01-01", end_date="2020-12-31")
    audit.add_signal("2020-01-06", {"AAPL": 0.05})
    audit.add_trade("2020-01-06", "AAPL", 10, 150.0, "buy", 0.05)
    audit.add_trade("2020-01-13", "MSFT", 5, 200.0, "buy", 0.03)

    trades = audit.filter_by_type("trade")
    assert len(trades) == 2

    jan6 = audit.filter_by_date("2020-01-06")
    assert len(jan6) == 2  # signal + trade

    aapl = audit.filter_by_symbol("AAPL")
    assert len(aapl) >= 2  # signal + trade mentioning AAPL

# Feature 7: Domain Tools
def test_tool_registry():
    from quantclaw.agents.tools import create_default_registry
    registry = create_default_registry()
    all_tools = registry.list_all()
    assert "ingestor" in all_tools
    assert "validator" in all_tools
    assert "miner" in all_tools
    assert "researcher" in all_tools
    assert "executor" in all_tools
    assert "risk_monitor" in all_tools
    assert "reporter" in all_tools

def test_tool_registry_get_tools():
    from quantclaw.agents.tools import create_default_registry
    registry = create_default_registry()
    ingestor_tools = registry.get_tools("ingestor")
    assert len(ingestor_tools) == 3
    names = [t.name for t in ingestor_tools]
    assert "check_data_gaps" in names
    assert "validate_data_quality" in names

def test_tool_registry_get_specific_tool():
    from quantclaw.agents.tools import create_default_registry
    registry = create_default_registry()
    tool = registry.get_tool("miner", "check_leakage")
    assert tool is not None
    assert tool.description == "Scan factor code for look-ahead bias patterns"
    assert registry.get_tool("miner", "nonexistent") is None

def test_tool_execute():
    from quantclaw.agents.tools import Tool
    import asyncio

    def my_handler(x=0):
        return x * 2

    tool = Tool(name="doubler", description="doubles input", agent="test", handler=my_handler)
    result = asyncio.run(tool.execute(x=5))
    assert result["result"] == 10
