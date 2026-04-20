"""Tests for programmatic narration."""
from quantclaw.orchestration.narration import narrate_step
from quantclaw.agents.base import AgentResult, AgentStatus


def test_narrate_validator():
    result = AgentResult(status=AgentStatus.SUCCESS, data={
        "sharpe": 1.5, "annual_return": 0.18, "max_drawdown": -0.08,
    })
    text = narrate_step("validator", result)
    assert "1.5" in text
    assert "18" in text


def test_narrate_miner():
    result = AgentResult(status=AgentStatus.SUCCESS, data={
        "factors": [{"name": "mom", "metrics": {"sharpe": 1.2}}],
    })
    text = narrate_step("miner", result)
    assert "1 factor" in text


def test_narrate_trainer():
    result = AgentResult(status=AgentStatus.SUCCESS, data={
        "model_type": "gradient_boosting", "sharpe": 1.1,
        "metrics": {"overfit_ratio": 1.5},
    })
    text = narrate_step("trainer", result)
    assert "gradient_boosting" in text


def test_narrate_researcher():
    result = AgentResult(status=AgentStatus.SUCCESS, data={
        "findings": [{"topic": "a"}, {"topic": "b"}],
    })
    text = narrate_step("researcher", result)
    assert "2" in text


def test_narrate_ingestor():
    result = AgentResult(status=AgentStatus.SUCCESS, data={
        "ohlcv": {"AAPL": {"rows": 100}, "MSFT": {"rows": 120}},
    })
    text = narrate_step("ingestor", result)
    assert "2 symbols" in text


def test_narrate_ingestor_partial_failure():
    result = AgentResult(status=AgentStatus.SUCCESS, data={
        "ohlcv": {
            "AAPL": {"rows": 100},
            "MSFT": {"error": "No data returned from any plugin"},
        },
    })
    text = narrate_step("ingestor", result)
    assert "1 symbol" in text
    assert "1 failed" in text


def test_narrate_unknown_agent():
    result = AgentResult(status=AgentStatus.SUCCESS, data={})
    text = narrate_step("unknown_agent", result)
    assert "completed" in text
