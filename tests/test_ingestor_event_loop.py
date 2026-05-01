"""Regression test: auto-ingest must not block the asyncio event loop.

Background: data plugins (WorldBank, FRED, etc.) implement DataPlugin
synchronously and use ``requests.get``. Before the fix, ingestor called
them directly from an ``async def``, blocking the event loop for the
duration of every HTTP call — which made WS broadcasts stall, /api/health
time out, and the dashboard floor go dark for tens of minutes per cycle.

This test proves the loop stays responsive during ingestion by running
an unrelated heartbeat coroutine in parallel and asserting it ticks.
"""
from __future__ import annotations
import asyncio
import time

import pandas as pd
import pytest

from quantclaw.agents.ingestor import IngestorAgent, FREE_PLUGINS


class _SlowSyncPlugin:
    """Stand-in for a real DataPlugin whose ``fetch_ohlcv`` blocks for a
    measurable time — emulates a slow remote API like WorldBank."""

    name = "data_test_slow"

    def __init__(self, blocking_seconds: float = 0.3) -> None:
        self._blocking = blocking_seconds

    def list_symbols(self) -> list[str]:
        return ["A", "B", "C"]

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        # Synchronous sleep — this is what blocks the event loop when
        # called directly from an async context. Wrapping in
        # asyncio.to_thread (as the fix does) restores responsiveness.
        time.sleep(self._blocking)
        return pd.DataFrame(
            {"close": [1.0, 2.0]},
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )


@pytest.mark.asyncio
async def test_auto_ingest_does_not_block_event_loop(monkeypatch):
    plugin = _SlowSyncPlugin(blocking_seconds=0.3)

    # Make our test plugin discoverable as a free source via the
    # PluginManager cache that ``_auto_ingest_free_sources`` queries.
    plugin_name = "data_test_slow"
    monkeypatch.setattr("quantclaw.agents.ingestor.FREE_PLUGINS", FREE_PLUGINS | {plugin_name})

    class _StubManager:
        def discover(self) -> None: pass
        def get(self, kind: str, name: str):
            return plugin if name == plugin_name else None

    monkeypatch.setattr("quantclaw.plugins.manager.PluginManager", _StubManager)

    agent = IngestorAgent(
        config={"plugins": {"data": [plugin_name]}},
        bus=None,
    )

    # Heartbeat: ticks once every 50ms while ingestion runs. If the
    # event loop is blocked, ticks pause and we count fewer than expected.
    ticks: list[float] = []
    stop = asyncio.Event()

    async def heartbeat():
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    hb_task = asyncio.create_task(heartbeat())
    try:
        result = await agent._auto_ingest_free_sources(start=None, end="2024-12-31")
    finally:
        stop.set()
        await hb_task

    assert plugin_name in result, "Auto-ingest should have collected our plugin"
    assert result[plugin_name]["series_count"] == 3

    # 3 sequential 0.3s sleeps in a thread = ~0.9s wall clock. Heartbeat
    # at 50ms intervals = ~18 ticks expected. Allow generous margin for
    # CI jitter — if the loop were blocked we'd see 1-2 ticks tops.
    assert len(ticks) >= 8, (
        f"Event loop appears blocked during ingestion — only {len(ticks)} "
        f"heartbeat ticks fired. With async to_thread wrapping in place we "
        f"should see ~18 ticks for a ~0.9s ingest."
    )


@pytest.mark.asyncio
async def test_ingest_one_plugin_sync_is_actually_synchronous():
    """The factored sync helper must not reach for ``await`` — that's
    its contract, since we're handing it to ``asyncio.to_thread``."""
    import inspect

    # Method should be a regular function, not a coroutine.
    method = IngestorAgent._ingest_one_plugin_sync
    assert not inspect.iscoroutinefunction(method), (
        "_ingest_one_plugin_sync must be sync — wrapping a coroutine in "
        "to_thread is a bug that crashes at runtime."
    )
