import pytest
from quantclaw.plugins.builtin.data_yfinance import YFinanceDataPlugin
from quantclaw.plugins.builtin.asset_us_equities import USEquitiesAssetPlugin
from quantclaw.plugins.builtin.engine_builtin import BuiltinEnginePlugin
from quantclaw.plugins.builtin.broker_ib import IBBrokerPlugin
import pandas as pd
import numpy as np


def test_yfinance_list_symbols():
    plugin = YFinanceDataPlugin()
    symbols = plugin.list_symbols()
    assert len(symbols) > 10
    assert "AAPL" in symbols


def test_yfinance_validate_key():
    plugin = YFinanceDataPlugin()
    assert plugin.validate_key() is True


def test_us_equities_default_universe():
    plugin = USEquitiesAssetPlugin()
    universe = plugin.get_default_universe()
    assert len(universe) >= 50
    assert "SPY" in universe


def test_us_equities_trading_hours():
    plugin = USEquitiesAssetPlugin()
    hours = plugin.get_trading_hours()
    assert hours.market_open == "09:30"
    assert hours.timezone == "US/Eastern"


def test_ib_broker_paper_default():
    plugin = IBBrokerPlugin()
    plugin.connect({"paper": True})
    account = plugin.get_account()
    assert account.equity == 100000


def test_builtin_engine_backtest():
    class SimpleStrategy:
        name = "test"
        universe = ["A", "B"]
        frequency = "weekly"

        def signals(self, data):
            return {"A": 1.0, "B": 0.5}

        def allocate(self, signals, portfolio):
            return {"A": 0.5, "B": 0.3}

    dates = pd.bdate_range("2023-01-01", "2023-12-31")
    np.random.seed(42)
    data = {
        "A": pd.DataFrame(
            {
                "open": 100,
                "high": 102,
                "low": 99,
                "close": np.random.uniform(95, 110, len(dates)),
                "volume": 1000000,
            },
            index=dates,
        ),
        "B": pd.DataFrame(
            {
                "open": 50,
                "high": 52,
                "low": 49,
                "close": np.random.uniform(45, 55, len(dates)),
                "volume": 500000,
            },
            index=dates,
        ),
    }

    engine = BuiltinEnginePlugin()
    result = engine.backtest(SimpleStrategy(), data, {"initial_capital": 100000})
    assert result.sharpe is not None
    assert len(result.equity_curve) > 0
    assert result.total_trades > 0
