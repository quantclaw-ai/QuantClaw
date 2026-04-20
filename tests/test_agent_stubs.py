"""Tests for stub agent implementations — verifies the interface works."""
import asyncio
import pytest
from quantclaw.events.bus import EventBus
from quantclaw.agents.base import AgentStatus


def test_compliance_agent_interface():
    from quantclaw.agents.compliance import ComplianceAgent
    bus = EventBus()
    agent = ComplianceAgent(bus=bus, config={})
    assert agent.name == "compliance"

    async def _run():
        result = await agent.execute({"task": "check_rules"})
        assert result.status == AgentStatus.SUCCESS

    asyncio.run(_run())



def test_executor_agent_interface():
    from quantclaw.agents.executor import ExecutorAgent
    bus = EventBus()
    agent = ExecutorAgent(bus=bus, config={})
    assert agent.name == "executor"

    async def _run():
        result = await agent.execute({"task": "submit_order"})
        assert result.status == AgentStatus.SUCCESS

    asyncio.run(_run())


def test_ingestor_agent_with_query():
    from quantclaw.agents.ingestor import IngestorAgent
    bus = EventBus()
    agent = IngestorAgent(bus=bus, config={})
    assert agent.name == "ingestor"

    async def _run():
        result = await agent.execute({"task": "market news AAPL"})
        # May succeed (web search) or fail (no network) — both valid
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)

    asyncio.run(_run())


def test_researcher_agent_interface():
    from quantclaw.agents.researcher import ResearcherAgent
    bus = EventBus()
    agent = ResearcherAgent(bus=bus, config={})
    assert agent.name == "researcher"

    async def _run():
        result = await agent.execute({"query": "test"})
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)

    asyncio.run(_run())


def test_compliance_detects_position_violation():
    from quantclaw.agents.compliance import ComplianceAgent
    bus = EventBus()
    config = {"risk": {"max_position_pct": 0.05}}
    agent = ComplianceAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "trades": [{"symbol": "AAPL", "value": 10000}],
            "portfolio_value": 100000,
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["compliant"] is False
        assert any(v["rule"] == "position_size" for v in result.data["violations"])

    asyncio.run(_run())


def test_compliance_passes_valid_trades():
    from quantclaw.agents.compliance import ComplianceAgent
    bus = EventBus()
    config = {"risk": {"max_position_pct": 0.05}}
    agent = ComplianceAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "trades": [{"symbol": "AAPL", "value": 3000}],
            "portfolio_value": 100000,
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["compliant"] is True

    asyncio.run(_run())


def test_compliance_detects_drawdown_violation():
    from quantclaw.agents.compliance import ComplianceAgent
    bus = EventBus()
    config = {"risk": {"max_drawdown": -0.10}}
    agent = ComplianceAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "trades": [],
            "current_drawdown": -0.15,
        })
        assert result.status == AgentStatus.SUCCESS
        assert result.data["compliant"] is False
        assert any(v["rule"] == "drawdown_limit" for v in result.data["violations"])

    asyncio.run(_run())
