"""Plugin interfaces for brokers, data, engines, and asset classes."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import pandas as pd


@dataclass
class Position:
    symbol: str
    qty: float
    avg_cost: float
    current_price: float
    unrealized_pnl: float


@dataclass
class Order:
    symbol: str
    qty: float
    side: str
    type: str
    limit_price: float | None = None


@dataclass
class OrderResult:
    order_id: str
    status: str
    filled_qty: float
    filled_price: float


@dataclass
class Account:
    equity: float
    cash: float
    buying_power: float
    positions: list[Position]


@dataclass
class TradingHours:
    market_open: str
    market_close: str
    timezone: str
    trading_days: list[int]


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    sharpe: float
    annual_return: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    metadata: dict = field(default_factory=dict)


class BrokerPlugin(ABC):
    name: str = "base_broker"

    @abstractmethod
    def connect(self, credentials: dict) -> None: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def submit_order(self, order: Order) -> OrderResult: ...

    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def is_market_open(self) -> bool: ...


class DataPlugin(ABC):
    name: str = "base_data"

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame: ...

    @abstractmethod
    def fetch_fundamentals(self, symbol: str) -> dict: ...

    @abstractmethod
    def list_symbols(self) -> list[str]: ...

    @abstractmethod
    def validate_key(self) -> bool: ...

    def available_fields(self) -> dict[str, list[str]]:
        """Return available field categories and their column names.

        Example: {"ohlcv": ["open","high","low","close","volume"],
                  "fundamentals": ["trailingPE","forwardPE",...]}
        """
        return {"ohlcv": ["open", "high", "low", "close", "volume"]}

    def field_history_modes(self) -> dict[str, str]:
        """Return how each field behaves historically.

        Supported modes:
        - "time_series": field values vary over time and should limit lookback
        - "snapshot": field is a point-in-time snapshot broadcast over rows and
          should not be treated as true historical depth
        """
        return {}

    def history_probe_start(self, freq: str = "1d") -> str:
        """Earliest safe date to use when probing provider history depth.

        The default avoids negative Unix timestamps for providers that convert
        request dates to seconds since epoch.
        """
        return "1970-01-01"

    def fetch_fields(self, symbol: str, fields: list[str],
                     start: str = "", end: str = "") -> pd.DataFrame:
        """Fetch specific fields for a symbol. Returns a DataFrame
        with requested columns merged on the date index.

        Fields can be time-series (joined to OHLCV dates) or
        scalar (broadcast across all rows).
        """
        return pd.DataFrame()


class EnginePlugin(ABC):
    name: str = "base_engine"

    @abstractmethod
    def backtest(self, strategy: Any, data: dict[str, pd.DataFrame], config: dict) -> BacktestResult: ...


class AssetPlugin(ABC):
    name: str = "base_asset"

    @abstractmethod
    def get_default_universe(self) -> list[str]: ...

    @abstractmethod
    def get_trading_hours(self) -> TradingHours: ...

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> dict: ...
