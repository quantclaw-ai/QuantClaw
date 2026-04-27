"""Tests for sandbox runner script."""
import asyncio
import json
import pytest
from pathlib import Path
from quantclaw.sandbox.sandbox import Sandbox


def test_strategy_runner():
    """Test execute_strategy with a simple strategy."""
    import pandas as pd
    import numpy as np

    sandbox = Sandbox(config={})

    # Create fake OHLCV data
    dates = pd.date_range("2023-01-01", periods=100, freq="B")
    data = {
        "AAPL": pd.DataFrame({
            "open": np.random.uniform(150, 160, 100),
            "high": np.random.uniform(160, 170, 100),
            "low": np.random.uniform(140, 150, 100),
            "close": np.random.uniform(150, 160, 100),
            "volume": np.random.randint(1000000, 5000000, 100),
        }, index=dates),
    }

    strategy_code = '''
class Strategy:
    name = "test_momentum"
    description = "Simple test"
    universe = ["AAPL"]
    frequency = "weekly"

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=20)
            if len(df) >= 5:
                scores[symbol] = float(df["close"].iloc[-1] / df["close"].iloc[-5] - 1)
        return scores

    def allocate(self, scores, portfolio):
        return {s: 1.0 for s in scores}

    def risk_check(self, orders, portfolio):
        return True
'''

    async def _run():
        result = await sandbox.execute_strategy(
            strategy_code=strategy_code,
            data=data,
            config={"initial_capital": 100000},
            timeout=30,
        )
        assert result.status == "ok", f"Failed: {result.stderr}"
        assert result.result is not None
        assert "sharpe" in result.result
        assert "annual_return" in result.result
        assert "max_drawdown" in result.result
        assert "total_trades" in result.result

    asyncio.run(_run())


def test_strategy_runner_bad_code():
    """Test execute_strategy with code that has no Strategy class."""
    import pandas as pd

    sandbox = Sandbox(config={})

    async def _run():
        result = await sandbox.execute_strategy(
            strategy_code="x = 1",
            data={},
            config={},
            timeout=10,
        )
        assert result.status == "error"

    asyncio.run(_run())


def test_strategy_runner_blocks_forbidden_imports():
    """execute_strategy must enforce the same import guard as execute_code."""
    sandbox = Sandbox(config={})
    strategy_code = '''
import subprocess

class Strategy:
    universe = ["AAPL"]

    def signals(self, data):
        subprocess.run(["python", "--version"], capture_output=True)
        return {"AAPL": 1.0}

    def allocate(self, scores, portfolio):
        return {"AAPL": 1.0}
'''

    async def _run():
        result = await sandbox.execute_strategy(
            strategy_code=strategy_code,
            data={},
            config={},
            timeout=10,
        )
        assert result.status == "error"
        assert "Security violation" in result.stderr
        assert any("subprocess" in warning for warning in result.import_warnings)

    asyncio.run(_run())
