"""Tests for the Playbook persistent memory store."""
import asyncio
import json
import os
import tempfile

import pytest

from quantclaw.orchestration.playbook import Playbook, PlaybookEntry, EntryType


@pytest.fixture
def tmp_playbook(tmp_path):
    return str(tmp_path / "playbook.jsonl")


def test_add_entry_and_query(tmp_playbook):
    pb = Playbook(tmp_playbook)

    async def _run():
        await pb.add(EntryType.STRATEGY_RESULT, {
            "strategy": "momentum_5d",
            "sharpe": 1.8,
            "annual_return": 0.22,
        }, tags=["momentum", "equity"])

        results = await pb.query(tags=["momentum"])
        assert len(results) == 1
        assert results[0].content["sharpe"] == 1.8
        assert results[0].entry_type == EntryType.STRATEGY_RESULT

    asyncio.run(_run())


def test_persistence_across_instances(tmp_playbook):
    async def _run():
        pb1 = Playbook(tmp_playbook)
        await pb1.add(EntryType.MARKET_OBSERVATION, {
            "observation": "VIX > 30 correlates with momentum crashes",
        }, tags=["vix", "momentum"])

        pb2 = Playbook(tmp_playbook)
        results = await pb2.query(tags=["vix"])
        assert len(results) == 1

    asyncio.run(_run())


def test_query_by_type(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        await pb.add(EntryType.STRATEGY_RESULT, {"strategy": "mean_rev"}, tags=["equity"])
        await pb.add(EntryType.WHAT_FAILED, {"strategy": "bad_idea", "reason": "overfitting"}, tags=["equity"])

        results = await pb.query(entry_type=EntryType.WHAT_FAILED)
        assert len(results) == 1
        assert results[0].content["reason"] == "overfitting"

    asyncio.run(_run())


def test_full_text_search(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        await pb.add(EntryType.MARKET_OBSERVATION, {
            "observation": "Federal Reserve rate hike signals bearish equities",
        }, tags=["fed", "rates"])

        results = await pb.search("Federal Reserve")
        assert len(results) == 1

    asyncio.run(_run())


def test_recent_entries(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        for i in range(10):
            await pb.add(EntryType.STRATEGY_RESULT, {"idx": i}, tags=["batch"])

        recent = await pb.recent(5)
        assert len(recent) == 5
        assert recent[-1].content["idx"] == 9  # most recent last

    asyncio.run(_run())


def test_factor_library_entry(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        await pb.add(EntryType.FACTOR_LIBRARY, {
            "name": "momentum_5d_vol_adj",
            "hypothesis": "5-day momentum adjusted for volatility captures short-term trends",
            "code": "df['close'].pct_change(5) / df['close'].pct_change(5).rolling(20).std()",
            "metrics": {"ic": 0.05, "rank_ic": 0.08, "sharpe": 1.2},
            "lineage": {"parent": None, "generation": 0, "method": "exploration"},
        }, tags=["factor", "momentum", "volatility"])

        factors = await pb.query(entry_type=EntryType.FACTOR_LIBRARY)
        assert len(factors) == 1
        assert factors[0].content["metrics"]["sharpe"] == 1.2

    asyncio.run(_run())
