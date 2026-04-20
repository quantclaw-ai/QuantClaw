"""Tests for Playbook compaction (snapshot + tail strategy)."""
import asyncio
import gzip
import json

import pytest

from quantclaw.orchestration.playbook import EntryType, Playbook


def _run(coro):
    return asyncio.run(coro)


def test_compaction_triggers_on_size_threshold(tmp_path):
    pb_path = tmp_path / "playbook.jsonl"
    pb = Playbook(
        path=str(pb_path),
        max_file_bytes=500,     # tiny so we trip quickly
        max_entries=10_000,
        compact_check_every=1,  # check on every write
    )

    async def _add_many():
        for i in range(30):
            await pb.add(
                EntryType.STRATEGY_RESULT,
                {"strategy_id": f"s{i}", "sharpe": 0.5 + i * 0.01},
                tags=["backtest"],
            )

    _run(_add_many())

    archives = list(tmp_path.glob("playbook.jsonl.archive.*.gz"))
    assert len(archives) >= 1, "compaction did not produce an archive"

    # The live file should now be smaller than the pre-compaction sum.
    size_after = pb_path.stat().st_size
    assert size_after > 0
    # Archive contains the full history.
    with gzip.open(archives[0], "rt", encoding="utf-8") as f:
        archive_lines = [json.loads(line) for line in f if line.strip()]
    assert any(row["content"]["strategy_id"] == "s0" for row in archive_lines)


def test_compaction_keeps_latest_snapshot_per_campaign(tmp_path):
    """campaign_state entries should dedupe by campaign_id — keep only latest."""
    pb = Playbook(
        path=str(tmp_path / "playbook.jsonl"),
        max_file_bytes=1,       # force immediate compaction
        max_entries=1,
        compact_check_every=1,
    )

    async def _add():
        for i in range(5):
            await pb.add(
                EntryType.CAMPAIGN_STATE,
                {"campaign_id": "camp-1", "phase": "discover", "cycle": i},
            )
        # Different campaign — should survive compaction separately.
        await pb.add(
            EntryType.CAMPAIGN_STATE,
            {"campaign_id": "camp-2", "phase": "paper", "cycle": 0},
        )

    _run(_add())

    async def _read():
        return await pb.query(entry_type=EntryType.CAMPAIGN_STATE)

    pb.invalidate()
    entries = _run(_read())
    ids_to_cycles = {e.content["campaign_id"]: e.content["cycle"] for e in entries}
    # Only latest cycle for camp-1 survives in the live log.
    assert ids_to_cycles["camp-1"] == 4
    assert ids_to_cycles["camp-2"] == 0


def test_no_compaction_below_threshold(tmp_path):
    pb_path = tmp_path / "playbook.jsonl"
    pb = Playbook(
        path=str(pb_path),
        max_file_bytes=1_000_000,
        max_entries=1000,
        compact_check_every=10,
    )

    async def _add():
        for i in range(5):
            await pb.add(EntryType.STRATEGY_RESULT, {"i": i})

    _run(_add())

    archives = list(tmp_path.glob("playbook.jsonl.archive.*.gz"))
    assert len(archives) == 0


def test_compaction_preserves_queryability(tmp_path):
    """After compaction, query() and recent() must still work."""
    pb = Playbook(
        path=str(tmp_path / "playbook.jsonl"),
        max_file_bytes=200,
        max_entries=20,
        compact_check_every=1,
    )

    async def _go():
        for i in range(50):
            await pb.add(EntryType.STRATEGY_RESULT, {"i": i}, tags=["mine"])
        latest = await pb.recent(n=5)
        return latest

    latest = _run(_go())
    assert len(latest) == 5
    # Because we kept the tail, the last entries should have the highest i.
    assert latest[-1].content["i"] == 49
