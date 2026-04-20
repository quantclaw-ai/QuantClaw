"""Tests for Reporter agent."""
import asyncio

import pytest

from quantclaw.agents.reporter import ReporterAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_reporter_formats_performance():
    bus = EventBus()
    agent = ReporterAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "summarize",
            "_upstream_results": {
                "0": {
                    "sharpe": 1.4,
                    "annual_return": 0.22,
                    "max_drawdown": -0.08,
                    "total_trades": 48,
                    "win_rate": 0.58,
                },
            },
        })
        assert result.status == AgentStatus.SUCCESS
        assert "1.40" in result.data["report"]
        assert "22.0%" in result.data["report"]

    asyncio.run(_run())


def test_reporter_formats_model():
    bus = EventBus()
    agent = ReporterAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "summarize",
            "_upstream_results": {
                "0": {
                    "model_type": "gradient_boosting",
                    "features_used": ["momentum_5d", "vol_20d"],
                    "metrics": {
                        "overfit_ratio": 1.64,
                        "test_accuracy": 0.54,
                    },
                },
            },
        })
        assert result.status == AgentStatus.SUCCESS
        assert "gradient_boosting" in result.data["report"]
        assert "momentum_5d" in result.data["report"]

    asyncio.run(_run())


def test_reporter_formats_factors():
    bus = EventBus()
    agent = ReporterAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "summarize",
            "_upstream_results": {
                "0": {
                    "factors": [
                        {
                            "name": "mom_5d",
                            "metrics": {"sharpe": 1.2, "ic": 0.05},
                        },
                    ],
                },
            },
        })
        assert result.status == AgentStatus.SUCCESS
        assert "mom_5d" in result.data["report"]
        assert "1 discovered" in result.data["report"]

    asyncio.run(_run())


def test_reporter_empty_data():
    bus = EventBus()
    agent = ReporterAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "summarize",
            "_upstream_results": {},
        })
        assert result.status == AgentStatus.SUCCESS

    asyncio.run(_run())


def test_reporter_interface():
    bus = EventBus()
    agent = ReporterAgent(bus=bus, config={})
    assert agent.name == "reporter"
