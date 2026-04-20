"""Tests for factor evaluation metrics."""
import pytest
import numpy as np
import pandas as pd
from quantclaw.sandbox.factor_evaluator import evaluate_factor


def test_evaluate_factor_basic():
    dates = pd.date_range("2023-01-01", periods=100, freq="B")
    close = np.cumsum(np.random.randn(100)) + 100
    data = {"AAPL": pd.DataFrame({"close": close}, index=dates)}
    scores = {"AAPL": pd.Series(close, index=dates).pct_change(5).shift(-5).dropna()}

    metrics = evaluate_factor(scores, data, forward_period=5)
    assert "ic" in metrics
    assert "rank_ic" in metrics
    assert "turnover" in metrics
    assert "sharpe" in metrics


def test_evaluate_factor_returns_numbers():
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    data = {"AAPL": pd.DataFrame({"close": np.random.uniform(150, 160, 50)}, index=dates)}
    scores = {"AAPL": pd.Series(np.random.randn(50), index=dates)}

    metrics = evaluate_factor(scores, data, forward_period=5)
    assert isinstance(metrics["ic"], float)
    assert isinstance(metrics["rank_ic"], float)
    assert isinstance(metrics["sharpe"], float)


def test_evaluate_factor_empty_scores():
    metrics = evaluate_factor({}, {}, forward_period=5)
    assert metrics["ic"] == 0.0
    assert metrics["sharpe"] == 0.0
