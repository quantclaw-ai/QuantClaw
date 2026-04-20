"""Tests for Trainer agent."""
import asyncio
import pytest
from quantclaw.agents.trainer import TrainerAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_trainer_interface():
    bus = EventBus()
    agent = TrainerAgent(bus=bus, config={})
    assert agent.name == "trainer"


def test_trainer_checks_dependencies():
    bus = EventBus()
    agent = TrainerAgent(bus=bus, config={})
    missing = agent._check_dependencies("gradient_boosting")
    assert missing == []


def test_trainer_detects_missing_deps():
    bus = EventBus()
    agent = TrainerAgent(bus=bus, config={})
    missing = agent._check_dependencies("lstm")
    assert isinstance(missing, list)


def test_trainer_extracts_upstream_factors():
    bus = EventBus()
    agent = TrainerAgent(bus=bus, config={})
    factors = agent._extract_factors({
        "factors": [],
        "_upstream_results": {
            "2": {"factors": [{"name": "mom", "code": "df['close'].pct_change(5)"}]},
        },
    })
    assert len(factors) == 1
    assert factors[0]["name"] == "mom"


def test_trainer_fails_gracefully_no_factors():
    bus = EventBus()
    agent = TrainerAgent(bus=bus, config={"sandbox": {"enabled": True, "timeout": 10}})

    async def _run():
        result = await agent.execute({
            "task": "train_model",
            "factors": [],
            "symbols": [],
            "model_type": "gradient_boosting",
        })
        assert result.status == AgentStatus.FAILED
        assert "No factors" in result.error

    asyncio.run(_run())
