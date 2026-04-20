"""Tests for workflow template matching."""
from quantclaw.orchestration.workflows import match_workflow, plan_from_template


def test_match_factor_discovery():
    result = match_workflow("find me alpha strategies")
    assert result is not None
    assert result["name"] == "factor_discovery"


def test_match_backtest():
    result = match_workflow("backtest the momentum strategy")
    assert result is not None
    assert result["name"] == "strategy_backtest"


def test_match_research():
    result = match_workflow("what's happening in the market today")
    assert result is not None
    assert result["name"] == "market_research"


def test_match_risk():
    result = match_workflow("check portfolio risk exposure")
    assert result is not None
    assert result["name"] == "risk_check"


def test_match_model_training():
    result = match_workflow("train a machine learning model on my data")
    assert result is not None
    assert result["name"] == "model_training"


def test_match_go_live():
    result = match_workflow("paper trade the winning strategy")
    assert result is not None
    assert result["name"] == "go_live"


def test_no_match_returns_none():
    result = match_workflow("hello how are you")
    assert result is None


def test_match_is_case_insensitive():
    result = match_workflow("FIND ME ALPHA")
    assert result is not None


def test_plan_from_template():
    template = match_workflow("find alpha")
    assert template is not None
    plan = plan_from_template(template, "find alpha")
    assert len(plan.steps) == 6
    assert plan.steps[0].agent == "researcher"
    assert plan.steps[2].agent == "miner"
    assert plan.steps[2].depends_on == [0, 1]
    assert "start" not in plan.steps[1].task
    assert "end" not in plan.steps[1].task
