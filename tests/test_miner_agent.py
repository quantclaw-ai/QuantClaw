"""Tests for Miner agent."""
import asyncio
import pytest
from quantclaw.agents.miner import MinerAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_miner_returns_factors_on_success():
    bus = EventBus()
    config = {"sandbox": {"enabled": True, "timeout": 30}}
    agent = MinerAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "task": "discover_factors",
            "goal": "find momentum alpha",
            "symbols": [],  # no symbols = skip evaluation, return raw factors
            "generations": 1,
        })
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)
        if result.status == AgentStatus.SUCCESS:
            assert "factors" in result.data
            assert len(result.data["factors"]) > 0

    asyncio.run(_run())


def test_miner_fallback_factors():
    """Without LLM, Miner uses fallback factor templates."""
    bus = EventBus()
    agent = MinerAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "discover_factors",
            "symbols": [],
        })
        assert result.status == AgentStatus.SUCCESS
        assert len(result.data["factors"]) == 4  # 4 fallback factors

    asyncio.run(_run())


def test_miner_interface():
    bus = EventBus()
    agent = MinerAgent(bus=bus, config={})
    assert agent.name == "miner"
