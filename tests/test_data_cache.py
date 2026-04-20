"""Tests for the range-aware OHLCV data cache."""
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

from quantclaw.plugins.data_cache import CachedDataPlugin
from quantclaw.plugins.interfaces import DataPlugin


class FakeDataPlugin(DataPlugin):
    """Counts fetch calls and records the (start, end) ranges asked for."""
    name = "fake"

    def __init__(self):
        self.call_count = 0
        self.calls: list[tuple[str, str, str]] = []

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        self.call_count += 1
        self.calls.append((symbol, start, end))
        idx = pd.date_range(start, end, freq="B", name="date")
        return pd.DataFrame({
            "open": range(len(idx)),
            "high": range(len(idx)),
            "low": range(len(idx)),
            "close": range(len(idx)),
            "volume": range(len(idx)),
        }, index=idx)

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {"pe_ratio": 25.0}

    def list_symbols(self) -> list[str]:
        return ["AAPL"]

    def validate_key(self) -> bool:
        return True


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "ohlcv_cache"
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_cache_miss_fetches_and_stores(cache_dir):
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    df = cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30")
    assert not df.empty
    assert inner.call_count == 1

    files = list((cache_dir / "1d").glob("*.parquet"))
    assert len(files) == 1
    assert files[0].name == "AAPL.parquet"


def test_exact_repeat_is_full_hit(cache_dir):
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    df1 = cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30")
    df2 = cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30")

    assert inner.call_count == 1
    assert len(df1) == len(df2)


def test_subset_is_full_hit(cache_dir):
    """If the cached range covers the request, no upstream call."""
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2014-12-31")
    inner.call_count = 0

    df = cached.fetch_ohlcv("AAPL", "2012-06-01", "2013-06-30")
    assert inner.call_count == 0
    assert not df.empty
    assert df.index.min() >= pd.Timestamp("2012-06-01")
    assert df.index.max() <= pd.Timestamp("2013-06-30")


def test_extension_after_only_fetches_new_tail(cache_dir):
    """Fetch [2010, 2012], then [2010, 2014] → only 2013-2014 is fetched."""
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2012-12-31")
    inner.calls.clear()
    inner.call_count = 0

    df = cached.fetch_ohlcv("AAPL", "2010-01-01", "2014-12-31")

    assert inner.call_count == 1
    # The new fetch should start AFTER the previous end, not at the original start.
    fetched_symbol, fetched_start, _ = inner.calls[0]
    assert fetched_symbol == "AAPL"
    assert pd.Timestamp(fetched_start) > pd.Timestamp("2012-12-31")
    # Result should still cover the entire requested range from cache.
    assert df.index.min() <= pd.Timestamp("2010-01-05")
    assert df.index.max() >= pd.Timestamp("2014-12-25")


def test_extension_before_only_fetches_new_head(cache_dir):
    """Fetch [2012, 2014], then [2010, 2014] → only 2010-2011 is fetched."""
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    cached.fetch_ohlcv("AAPL", "2012-01-01", "2014-12-31")
    inner.calls.clear()
    inner.call_count = 0

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2014-12-31")

    assert inner.call_count == 1
    _, _, fetched_end = inner.calls[0]
    # Gap-before must end strictly before the cached window's stored start
    # (which lands on the first business day on/after 2012-01-01).
    assert pd.Timestamp(fetched_end) <= pd.Timestamp("2012-01-01")


def test_extension_both_sides_fetches_two_ranges(cache_dir):
    """Cache has [2012, 2013], request [2010, 2015] → fetches before+after."""
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    cached.fetch_ohlcv("AAPL", "2012-01-01", "2013-12-31")
    inner.calls.clear()
    inner.call_count = 0

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2015-12-31")

    assert inner.call_count == 2
    starts = [pd.Timestamp(s) for _, s, _ in inner.calls]
    ends = [pd.Timestamp(e) for _, _, e in inner.calls]
    # One range before the existing window, one after.
    assert any(e <= pd.Timestamp("2012-01-01") for e in ends)
    assert any(s >= pd.Timestamp("2013-12-31") for s in starts)


def test_immutable_history_never_refetches(cache_dir):
    """Old historical data is never refetched even when mtime is stale."""
    inner = FakeDataPlugin()
    # stale_hours=-1 forces "always stale" by mtime; freeze_days=7 means anything
    # older than a week is immutable and should NOT trigger a refresh.
    cached = CachedDataPlugin(inner, cache_dir=cache_dir, stale_hours=-1, freeze_days=7)

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30")
    inner.call_count = 0

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30")
    assert inner.call_count == 0, "Frozen history should not be re-fetched"


def test_recent_data_refreshes_when_stale(cache_dir):
    """Requests reaching into the unfrozen window refetch the recent tail."""
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir, stale_hours=-1, freeze_days=7)

    today = pd.Timestamp.now().normalize()
    end = today.strftime("%Y-%m-%d")
    start = (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d")

    cached.fetch_ohlcv("AAPL", start, end)
    inner.calls.clear()
    inner.call_count = 0

    cached.fetch_ohlcv("AAPL", start, end)
    assert inner.call_count >= 1, "Mutable tail should refresh when stale"
    # At least one of the inner calls must target the unfrozen window
    # (within the last freeze_days). Other calls may be gap-before/after
    # depending on where the calendar lands relative to business days.
    refresh_window = today - pd.Timedelta(days=8)
    assert any(
        pd.Timestamp(call[1]) >= refresh_window for call in inner.calls
    ), f"No refresh call within freeze window: {inner.calls}"


def test_inventory_after_writes(cache_dir):
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2014-12-31")
    cached.fetch_ohlcv("MSFT", "2018-01-01", "2018-12-31")

    inv = cached.cached_inventory()
    assert "AAPL" in inv and "MSFT" in inv
    assert inv["AAPL"]["start"] == "2010-01-01"
    assert inv["MSFT"]["freq"] == "1d"
    assert inv["AAPL"]["rows"] > 0


def test_separate_freq_separate_files(cache_dir):
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30", freq="1d")
    cached.fetch_ohlcv("AAPL", "2010-01-01", "2010-06-30", freq="1h")

    daily = cache_dir / "1d" / "AAPL.parquet"
    hourly = cache_dir / "1h" / "AAPL.parquet"
    assert daily.exists()
    assert hourly.exists()


def test_cache_handles_tz_aware_and_tz_naive_data(cache_dir):
    """Reproduces the production "Cannot compare tz-naive and tz-aware" error.

    Crypto/FX feeds return DataFrames with tz-aware DatetimeIndex (UTC), while
    stock feeds return tz-naive. If both types share a cache, slicing or
    range comparison would crash. The fix strips tz at the cache boundary.
    """
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    # Patch FakeDataPlugin to return a tz-AWARE index this call.
    original_fetch = inner.fetch_ohlcv

    def fetch_with_tz(symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        df = original_fetch(symbol, start, end, freq)
        df.index = df.index.tz_localize("UTC")
        return df

    inner.fetch_ohlcv = fetch_with_tz  # type: ignore[assignment]

    # First fetch lands tz-aware data into the cache.
    df1 = cached.fetch_ohlcv("BTCUSD", "2023-01-01", "2023-06-30")
    assert not df1.empty

    # Second fetch with tz-NAIVE Timestamp boundaries (the request shape
    # ingestor uses) must not raise.
    df2 = cached.fetch_ohlcv("BTCUSD", "2023-02-01", "2023-05-31")
    assert not df2.empty
    assert df2.index.tz is None  # cache normalizes to naive


def test_passthrough_methods(cache_dir):
    inner = FakeDataPlugin()
    cached = CachedDataPlugin(inner, cache_dir=cache_dir)

    assert cached.name == "fake"
    assert cached.fetch_fundamentals("AAPL") == {"pe_ratio": 25.0}
    assert cached.list_symbols() == ["AAPL"]
    assert cached.validate_key() is True


def test_plugin_manager_wraps_data_plugins():
    from quantclaw.plugins.manager import PluginManager

    pm = PluginManager()
    pm.discover()
    plugin = pm.get("data", "data_yfinance")

    assert plugin is not None
    assert isinstance(plugin, CachedDataPlugin)
