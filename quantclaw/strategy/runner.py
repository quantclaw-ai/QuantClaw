"""Execute strategies via backtest or live trading."""
from __future__ import annotations
from quantclaw.strategy.loader import load_strategy
from quantclaw.plugins.manager import PluginManager
from quantclaw.plugins.interfaces import BacktestResult


class StrategyRunner:
    def __init__(self, plugin_manager: PluginManager, config: dict):
        self._pm = plugin_manager
        self._config = config

    def backtest(self, strategy_path: str, start: str = "2019-01-01", end: str = "2024-12-31") -> BacktestResult:
        strategy = load_strategy(strategy_path)
        universe = getattr(strategy, "universe", [])
        data_plugin_names = self._config.get("plugins", {}).get("data", ["data_yfinance"])
        if isinstance(data_plugin_names, str):
            data_plugin_names = [data_plugin_names]
        data_plugin = self._pm.get("data", data_plugin_names[0])
        if data_plugin is None:
            raise ValueError(f"No data plugin found: {data_plugin_names[0]}")
        data = {}
        for symbol in universe:
            df = data_plugin.fetch_ohlcv(symbol, start, end)
            if not df.empty:
                data[symbol] = df
        engine_name = self._config.get("plugins", {}).get("engine", "engine_builtin")
        engine = self._pm.get("engine", engine_name)
        if engine is None:
            raise ValueError(f"No engine plugin found: {engine_name}")
        return engine.backtest(strategy, data, self._config)
