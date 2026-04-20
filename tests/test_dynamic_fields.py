"""Tests for dynamic data field ingestion pipeline."""
import asyncio
import pytest
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_yfinance_available_fields():
    """yfinance plugin exposes OHLCV + fundamentals + sentiment + technical."""
    from quantclaw.plugins.builtin.data_yfinance import YFinanceDataPlugin

    plugin = YFinanceDataPlugin()
    fields = plugin.available_fields()

    assert "ohlcv" in fields
    assert "fundamentals" in fields
    assert "sentiment" in fields
    assert "technical" in fields
    assert "open" in fields["ohlcv"]
    assert "shortRatio" in fields["sentiment"]
    assert "returnOnEquity" in fields["fundamentals"]
    assert "beta" in fields["technical"]


def test_cached_plugin_exposes_available_fields():
    """CachedDataPlugin passes through available_fields()."""
    from quantclaw.plugins.manager import PluginManager
    from quantclaw.plugins.data_cache import CachedDataPlugin

    pm = PluginManager()
    pm.discover()
    plugin = pm.get("data", "data_yfinance")

    assert isinstance(plugin, CachedDataPlugin)
    fields = plugin.available_fields()
    assert "fundamentals" in fields
    assert "sentiment" in fields


def test_ingestor_extracts_suggested_fields():
    """Ingestor extracts suggested_data_sources from upstream Researcher."""
    from quantclaw.agents.ingestor import IngestorAgent

    bus = EventBus()
    agent = IngestorAgent(bus=bus, config={})

    # Simulate upstream Researcher output
    task = {
        "_upstream_results": {
            "0": {
                "findings": [],
                "suggested_factors": [],
                "suggested_models": [],
                "suggested_data_sources": ["ohlcv", "shortRatio", "beta", "returnOnEquity"],
            }
        }
    }
    fields = agent._extract_suggested_fields(task)
    assert "shortRatio" in fields
    assert "beta" in fields
    assert "returnOnEquity" in fields
    assert "ohlcv" not in fields  # ohlcv always fetched, should be filtered


def test_ingestor_handles_no_upstream():
    """Ingestor returns empty fields when no upstream."""
    from quantclaw.agents.ingestor import IngestorAgent

    bus = EventBus()
    agent = IngestorAgent(bus=bus, config={})
    assert agent._extract_suggested_fields({}) == []
    assert agent._extract_suggested_fields({"_upstream_results": {}}) == []


def test_miner_extracts_available_columns():
    """Miner reads columns list from upstream Ingestor."""
    from quantclaw.agents.miner import MinerAgent

    bus = EventBus()
    agent = MinerAgent(bus=bus, config={})

    task = {
        "_upstream_results": {
            "1": {
                "ohlcv": {"AAPL": {"rows": 500}},
                "columns": ["open", "high", "low", "close", "volume", "shortRatio", "beta"],
            }
        }
    }
    cols = agent._extract_available_columns(task)
    assert cols == ["open", "high", "low", "close", "volume", "shortRatio", "beta"]


def test_miner_defaults_to_ohlcv():
    """Without upstream, Miner defaults to OHLCV columns."""
    from quantclaw.agents.miner import MinerAgent

    bus = EventBus()
    agent = MinerAgent(bus=bus, config={})
    cols = agent._extract_available_columns({})
    assert cols == ["open", "high", "low", "close", "volume"]


def test_miner_extracts_extra_fields():
    """Miner identifies extra fields beyond OHLCV from upstream."""
    from quantclaw.agents.miner import MinerAgent

    bus = EventBus()
    agent = MinerAgent(bus=bus, config={})

    task = {
        "_upstream_results": {
            "1": {
                "columns": ["open", "high", "low", "close", "volume",
                            "shortRatio", "beta", "returnOnEquity"],
            }
        }
    }
    extra = agent._extract_extra_fields_from_upstream(task)
    assert "shortRatio" in extra
    assert "beta" in extra
    assert "returnOnEquity" in extra
    assert "close" not in extra
    assert "volume" not in extra


def test_researcher_gets_available_fields():
    """Researcher can query available fields from data plugin."""
    from quantclaw.agents.researcher import ResearcherAgent

    bus = EventBus()
    config = {"plugins": {"data": ["data_yfinance"]}}
    agent = ResearcherAgent(bus=bus, config=config)

    fields = agent._get_available_fields()
    assert "ohlcv" in fields
    assert "fundamentals" in fields
    assert "sentiment" in fields
