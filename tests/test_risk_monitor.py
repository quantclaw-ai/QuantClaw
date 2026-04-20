"""Tests for Risk Monitor agent."""
import asyncio
import pytest
from quantclaw.agents.risk_monitor import RiskMonitorAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_risk_monitor_clean_portfolio():
    bus = EventBus()
    config = {"risk": {"max_drawdown": -0.10}}
    agent = RiskMonitorAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "positions": [
                {"symbol": "AAPL", "weight": 0.05, "sector": "tech"},
                {"symbol": "MSFT", "weight": 0.05, "sector": "tech"},
                {"symbol": "JPM", "weight": 0.05, "sector": "finance"},
                {"symbol": "JNJ", "weight": 0.05, "sector": "health"},
            ],
            "equity": 100000,
            "current_drawdown": -0.03,
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["risk_level"] == "low"
        assert len(result.data["issues"]) == 0

    asyncio.run(_run())


def test_risk_monitor_detects_drawdown():
    bus = EventBus()
    config = {"risk": {"max_drawdown": -0.10}}
    agent = RiskMonitorAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "positions": [],
            "current_drawdown": -0.15,
        })
        assert result.data["risk_level"] == "critical"
        assert any(i["check"] == "drawdown" for i in result.data["issues"])

    asyncio.run(_run())


def test_risk_monitor_detects_concentration():
    bus = EventBus()
    agent = RiskMonitorAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "positions": [
                {"symbol": "AAPL", "weight": 0.25, "sector": "tech"},
                {"symbol": "MSFT", "weight": 0.20, "sector": "tech"},
                {"symbol": "GOOG", "weight": 0.15, "sector": "tech"},
            ],
        })
        assert any(i["check"] == "sector_concentration" for i in result.data["issues"])

    asyncio.run(_run())


def test_risk_monitor_detects_single_stock():
    bus = EventBus()
    agent = RiskMonitorAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "positions": [
                {"symbol": "TSLA", "weight": 0.15, "sector": "auto"},
            ],
        })
        assert any(i["check"] == "single_stock_exposure" for i in result.data["issues"])

    asyncio.run(_run())


def test_risk_monitor_detects_underdiversified():
    bus = EventBus()
    agent = RiskMonitorAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "positions": [
                {"symbol": "AAPL", "weight": 0.05, "sector": "tech"},
            ],
        })
        assert any(i["check"] == "underdiversified" for i in result.data["issues"])

    asyncio.run(_run())


def test_risk_monitor_interface():
    bus = EventBus()
    agent = RiskMonitorAgent(bus=bus, config={})
    assert agent.name == "risk_monitor"
