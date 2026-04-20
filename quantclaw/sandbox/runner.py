"""Bootstrap script for strategy backtest in subprocess.

Usage: python runner.py <temp_dir>

Reads:
  temp_dir/strategy.py    -- Strategy class
  temp_dir/data/*.parquet -- OHLCV data per symbol
  temp_dir/config.json    -- Backtest configuration

Outputs: JSON to stdout with backtest results.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: runner.py <temp_dir>"}))
        sys.exit(1)

    temp_dir = Path(sys.argv[1])

    # Load strategy
    strategy_path = temp_dir / "strategy.py"
    if not strategy_path.exists():
        print(json.dumps({"error": "strategy.py not found"}))
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("strategy_module", str(strategy_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "Strategy"):
        print(json.dumps({"error": "Strategy class not found in strategy.py"}))
        sys.exit(1)

    strategy = module.Strategy()

    # Load data
    data_dir = temp_dir / "data"
    data: dict[str, pd.DataFrame] = {}
    if data_dir.exists():
        for parquet_file in data_dir.glob("*.parquet"):
            symbol = parquet_file.stem
            data[symbol] = pd.read_parquet(parquet_file)

    # Load config
    config_path = temp_dir / "config.json"
    config: dict = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    # Run backtest using the built-in engine
    from quantclaw.plugins.builtin.engine_builtin import BuiltinEnginePlugin

    engine = BuiltinEnginePlugin()
    result = engine.backtest(strategy, data, config)

    # Serialize result to JSON
    output = {
        "sharpe": result.sharpe,
        "annual_return": result.annual_return,
        "max_drawdown": result.max_drawdown,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "signal_errors": result.metadata.get("signal_errors", 0) if result.metadata else 0,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
