"""Tests for dynamic market-data availability discovery."""
import asyncio

import pandas as pd

from quantclaw.agents.base import AgentStatus
from quantclaw.agents.ingestor import IngestorAgent
from quantclaw.agents.market_data import load_market_data
from quantclaw.events.bus import EventBus
from quantclaw.plugins.interfaces import DataPlugin


def _frame(start: str, end: str, *, value: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="B", name="date")
    return pd.DataFrame({
        "open": value,
        "high": value + 1,
        "low": value - 1,
        "close": value,
        "volume": 1000,
    }, index=dates)


def _patch_plugin_manager(monkeypatch, plugins: dict[str, DataPlugin]) -> None:
    class FakePluginManager:
        def discover(self):
            return None

        def get(self, plugin_type: str, name: str):
            if plugin_type != "data":
                return None
            return plugins.get(name)

    monkeypatch.setattr("quantclaw.plugins.manager.PluginManager", FakePluginManager)


class ShallowHistoryPlugin(DataPlugin):
    name = "data_yfinance"

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        df = _frame("2020-01-01", "2024-12-31", value=101.0)
        return df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {}

    def list_symbols(self) -> list[str]:
        return ["AAPL"]

    def validate_key(self) -> bool:
        return True


class DeepHistoryPlugin(DataPlugin):
    name = "data_stooq"

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        df = _frame("2010-01-01", "2024-12-31", value=102.0)
        return df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {}

    def list_symbols(self) -> list[str]:
        return ["AAPL"]

    def validate_key(self) -> bool:
        return True


class PriceWithShortFieldPlugin(DataPlugin):
    name = "data_yfinance"

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        df = _frame("2019-01-01", "2024-12-31", value=103.0)
        return df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {}

    def list_symbols(self) -> list[str]:
        return ["AAPL"]

    def validate_key(self) -> bool:
        return True

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "alternative": ["ark_weight"],
        }

    def field_history_modes(self) -> dict[str, str]:
        return {"ark_weight": "time_series"}

    def fetch_fields(self, symbol: str, fields: list[str], start: str = "", end: str = "") -> pd.DataFrame:
        if "ark_weight" not in fields:
            return pd.DataFrame()
        dates = pd.date_range("2021-01-04", "2024-12-31", freq="B", name="date")
        df = pd.DataFrame({"ark_weight": 0.25}, index=dates)
        start_ts = pd.Timestamp(start) if start else pd.Timestamp("1900-01-01")
        end_ts = pd.Timestamp(end) if end else pd.Timestamp("2100-01-01")
        return df[(df.index >= start_ts) & (df.index <= end_ts)]


def test_load_market_data_selects_deepest_provider(monkeypatch):
    _patch_plugin_manager(monkeypatch, {
        "data_yfinance": ShallowHistoryPlugin(),
        "data_stooq": DeepHistoryPlugin(),
    })

    config = {"plugins": {"data": ["data_yfinance", "data_stooq"]}}
    bundle = load_market_data(config, ["AAPL"], None, "2024-12-31")

    assert bundle.metadata["AAPL"]["source"] == "data_stooq"
    assert bundle.availability["summary"]["price_common_window"]["start"] == "2010-01-01"
    assert bundle.availability["summary"]["recommended_common_window"]["start"] == "2010-01-01"


def test_load_market_data_aligns_partial_field_history(monkeypatch):
    _patch_plugin_manager(monkeypatch, {"data_yfinance": PriceWithShortFieldPlugin()})

    config = {"plugins": {"data": ["data_yfinance"]}}
    bundle = load_market_data(
        config,
        ["AAPL"],
        None,
        "2024-12-31",
        extra_fields=["ark_weight"],
    )

    df = bundle.frames["AAPL"]
    assert "ark_weight" in df.columns
    assert df.loc[df.index < pd.Timestamp("2021-01-04"), "ark_weight"].isna().all()
    assert df.loc[df.index >= pd.Timestamp("2021-01-04"), "ark_weight"].notna().all()
    assert bundle.metadata["AAPL"]["field_history"]["ark_weight"]["start"] == "2021-01-04"
    assert bundle.availability["summary"]["field_common_window"]["start"] == "2021-01-04"
    assert bundle.availability["summary"]["recommended_common_window"]["start"] == "2021-01-04"


def test_ingestor_reports_availability_and_extra_field_history(monkeypatch):
    _patch_plugin_manager(monkeypatch, {"data_yfinance": PriceWithShortFieldPlugin()})

    bus = EventBus()
    agent = IngestorAgent(bus=bus, config={"plugins": {"data": ["data_yfinance"]}})

    async def _run():
        result = await agent.execute({
            "symbols": ["AAPL"],
            "_upstream_results": {
                "0": {"suggested_data_sources": ["ohlcv", "ark_weight"]},
            },
        })
        assert result.status == AgentStatus.SUCCESS
        assert "availability" in result.data
        assert result.data["availability"]["selection_mode"] == "max_history"
        assert result.data["recommended_window"]["start"] == "2021-01-04"
        assert "ark_weight" in result.data["columns"]
        assert result.data["extra_fields"]["AAPL"]["history"]["ark_weight"]["start"] == "2021-01-04"

    asyncio.run(_run())
