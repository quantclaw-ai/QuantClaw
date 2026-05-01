"""Tests for the legacy-cache-file prune that runs on startup.

The pre-merge cache layout wrote one parquet per (symbol, date-range,
hash); the current layout writes one parquet per (symbol, freq).
Legacy files linger on disk forever, never read. Pruning them at
startup keeps cache state matching the code's expectations.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd
import pytest

from quantclaw.plugins.data_cache import prune_legacy_cache_files


def _empty_parquet(path: Path) -> None:
    """Write a tiny valid parquet file at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2024-01-01"])).to_parquet(path)


def test_prune_deletes_legacy_files_keeps_modern(tmp_path):
    cache_dir = tmp_path / "cache"
    freq = cache_dir / "1d"
    freq.mkdir(parents=True)

    # Modern format — must survive.
    keep_files = [
        freq / "AAPL.parquet",
        freq / "MSFT.parquet",
        freq / "BRK_B.parquet",  # symbol with internal underscore (BRK.B → BRK_B)
    ]
    for p in keep_files:
        _empty_parquet(p)

    # Legacy format — must be deleted.
    legacy_files = [
        freq / "AAPL_1970-01-01_2026-04-19_1d_5d9bd1208cb5.parquet",
        freq / "AAPL_2020-01-01_2024-12-31_1d_b0bae4a899f1.parquet",
        freq / "TSLA_2010-06-29_2024-09-30_1d_47f3cad273e1.parquet",
        freq / "BRK_B_2020-01-01_2024-12-31_1d_deadbeef.parquet",  # underscore + date
    ]
    for p in legacy_files:
        _empty_parquet(p)

    removed = prune_legacy_cache_files(cache_dir)

    assert removed == len(legacy_files)
    for p in keep_files:
        assert p.exists(), f"modern file {p.name} should not have been pruned"
    for p in legacy_files:
        assert not p.exists(), f"legacy file {p.name} should have been deleted"


def test_prune_idempotent(tmp_path):
    """Calling twice on a clean cache returns 0 the second time."""
    cache_dir = tmp_path / "cache"
    freq = cache_dir / "1d"
    freq.mkdir(parents=True)
    _empty_parquet(freq / "AAPL_2020-01-01_2024-12-31_1d_aabbccdd.parquet")

    first = prune_legacy_cache_files(cache_dir)
    second = prune_legacy_cache_files(cache_dir)

    assert first == 1
    assert second == 0


def test_prune_handles_missing_cache_dir(tmp_path):
    """Fresh installs have no cache dir — prune must not raise."""
    nonexistent = tmp_path / "no-cache-here"
    assert prune_legacy_cache_files(nonexistent) == 0


def test_prune_ignores_non_parquet_files(tmp_path):
    """Random files in the cache dir (e.g., debug dumps, .DS_Store) are
    left alone even if their names happen to match the date pattern."""
    cache_dir = tmp_path / "cache"
    freq = cache_dir / "1d"
    freq.mkdir(parents=True)

    # Looks legacy-ish but not a parquet — must be left alone.
    other = freq / "AAPL_2020-01-01_2024-12-31_1d_aabbccdd.txt"
    other.write_text("notes")

    # Real legacy parquet sibling — should still be removed.
    real_legacy = freq / "AAPL_2020-01-01_2024-12-31_1d_aabbccdd.parquet"
    _empty_parquet(real_legacy)

    removed = prune_legacy_cache_files(cache_dir)

    assert removed == 1
    assert other.exists()
    assert not real_legacy.exists()
