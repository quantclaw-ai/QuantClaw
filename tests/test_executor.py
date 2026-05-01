"""Tests for Executor agent."""
import asyncio

import pandas as pd

from quantclaw.agents.base import AgentStatus
from quantclaw.agents.executor import ExecutorAgent
from quantclaw.events.bus import EventBus


def test_executor_paper_trade():
    bus = EventBus()
    config = {}
    agent = ExecutorAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "task": "submit_orders",
            "orders": [
                {"symbol": "AAPL", "side": "buy", "qty": 100, "price": 155.0},
            ],
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["mode"] == "paper"
        assert result.data["orders_executed"] == 1
        assert result.data["orders"][0]["status"] == "filled"

    asyncio.run(_run())


def test_executor_paper_no_orders():
    bus = EventBus()
    agent = ExecutorAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "submit_orders",
            "orders": [],
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["mode"] == "paper"
        assert result.data["orders_executed"] == 0

    asyncio.run(_run())


def test_executor_requires_live_trading_flag():
    """Broker config alone should still use paper trading unless live execution is explicit."""
    bus = EventBus()
    config = {"plugins": {"broker": "broker_ib"}}
    agent = ExecutorAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "task": "submit_orders",
            "orders": [{"symbol": "AAPL", "side": "buy", "qty": 10, "price": 155.0}],
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["mode"] == "paper"

    asyncio.run(_run())


def test_executor_interface():
    bus = EventBus()
    agent = ExecutorAgent(bus=bus, config={})
    assert agent.name == "executor"


def test_executor_runs_paper_deployments(monkeypatch, tmp_path):
    bus = EventBus()
    agent = ExecutorAgent(bus=bus, config={})

    strategy_file = tmp_path / "demo_strategy.py"
    strategy_file.write_text(
        """class Strategy:
    universe = ["AAPL"]
    frequency = "weekly"

    def signals(self, data):
        return {"AAPL": 1.0}

    def allocate(self, scores, portfolio):
        return {"AAPL": 1.0}
""",
        encoding="utf-8",
    )

    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    df = pd.DataFrame({
        "open": [100.0] * len(dates),
        "high": [101.0] * len(dates),
        "low": [99.0] * len(dates),
        "close": [100.0] * len(dates),
        "volume": [1000] * len(dates),
    }, index=dates)

    monkeypatch.setattr(
        agent,
        "_load_market_data",
        lambda symbols, start, end, extra_fields=None: {"AAPL": df},
    )

    async def _run():
        result = await agent.execute({
            "task": "run_deployments",
            "deployments": [{
                "id": "dep-1",
                "strategy_path": str(strategy_file),
                "allocation_pct": 1.0,
            }],
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["mode"] == "paper"
        assert result.data["orders_executed"] > 0
        assert result.data["deployment_updates"][0]["status"] == "ok"
        assert result.data["deployments_run"] == ["dep-1"]

    asyncio.run(_run())


def test_executor_reports_deployment_signal_errors(monkeypatch, tmp_path):
    bus = EventBus()
    agent = ExecutorAgent(bus=bus, config={})

    strategy_file = tmp_path / "fragile_strategy.py"
    strategy_file.write_text(
        """class Strategy:
    universe = ["AAPL"]
    frequency = "weekly"

    def signals(self, data):
        self._last_signal_errors = [{"symbol": "AAPL", "error": "missing feature"}]
        return {}

    def allocate(self, scores, portfolio):
        return {}
""",
        encoding="utf-8",
    )

    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    df = pd.DataFrame({
        "open": [100.0] * len(dates),
        "high": [101.0] * len(dates),
        "low": [99.0] * len(dates),
        "close": [100.0] * len(dates),
        "volume": [1000] * len(dates),
    }, index=dates)

    monkeypatch.setattr(
        agent,
        "_load_market_data",
        lambda symbols, start, end, extra_fields=None: {"AAPL": df},
    )

    async def _run():
        result = await agent.execute({
            "task": "run_deployments",
            "deployments": [{
                "id": "dep-1",
                "strategy_path": str(strategy_file),
                "allocation_pct": 1.0,
            }],
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["signal_errors"] == 1
        assert result.data["deployment_updates"][0]["signal_errors"] == 1

    asyncio.run(_run())
