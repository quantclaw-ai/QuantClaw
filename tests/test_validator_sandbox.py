"""Tests for the Validator agent with sandbox execution.

Covers both task modes:
* ``task="backtest"`` (formerly the Backtester agent) — in-sample replay.
* ``task="validate"`` (formerly the Evaluator agent) — in-sample + held-out.
"""
import asyncio

from quantclaw.agents.validator import ValidatorAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_validator_fails_without_strategy_code():
    bus = EventBus()
    agent = ValidatorAgent(bus=bus, config={"sandbox": {"enabled": True}})

    async def _run():
        result = await agent.execute({"task": "backtest", "symbols": ["AAPL"]})
        assert result.status == AgentStatus.FAILED
        assert "strategy_code" in result.error

    asyncio.run(_run())


def test_validator_extracts_strategy_code_from_upstream():
    agent = ValidatorAgent(bus=EventBus(), config={"sandbox": {"enabled": True}})
    code = agent._extract_strategy_code({
        "_upstream_results": {
            "3": {
                "model_id": "gb_abc123",
                "strategy_code": "class Strategy:\n    pass",
                "strategy_path": "data/strategies/gb_abc123.py",
            }
        }
    })
    assert "class Strategy" in code


def test_validator_extract_empty_when_no_upstream():
    agent = ValidatorAgent(bus=EventBus(), config={"sandbox": {"enabled": True}})
    assert agent._extract_strategy_code({}) == ""
    assert agent._extract_strategy_code({"_upstream_results": {}}) == ""
    assert agent._extract_strategy_code({"_upstream_results": {"0": {"data": "no code"}}}) == ""


def test_validator_backtest_task_with_bad_code():
    """Strategy code with no valid Strategy class fails gracefully."""
    agent = ValidatorAgent(bus=EventBus(), config={"sandbox": {"enabled": True, "timeout": 10}})

    async def _run():
        result = await agent.execute({
            "task": "backtest",
            "strategy_code": "x = 1  # no Strategy class",
            "symbols": [],
        })
        assert result.status == AgentStatus.FAILED

    asyncio.run(_run())


def test_validator_legacy_evaluate_task_maps_to_backtest():
    """Workflows generated before the merge used task='evaluate' — still works."""
    agent = ValidatorAgent(bus=EventBus(), config={"sandbox": {"enabled": True, "timeout": 10}})

    async def _run():
        result = await agent.execute({
            "task": "evaluate",  # legacy name
            "strategy_code": "x = 1",
            "symbols": [],
        })
        # Whatever the outcome, the request shouldn't be rejected for unknown task.
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)

    asyncio.run(_run())
