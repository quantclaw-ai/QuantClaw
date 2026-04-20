"""Range-aware disk cache for DataPlugin.fetch_ohlcv().

One parquet per (symbol, freq) under ``data/cache/ohlcv/{freq}/{symbol}.parquet``.
Each file is the union of every date range ever requested for that symbol —
new requests fetch only the missing portions and merge into the same file.

Two staleness tiers:

* **Immutable history.** Any data with ``date < today - freeze_days`` is
  treated as never-changing — once cached, it's never refetched (even when
  the file mtime is "stale").
* **Mutable tail.** When the request reaches into the recent ``freeze_days``
  window AND the file mtime is older than ``stale_hours``, the recent tail
  is refetched and merged. Older portions are left untouched.

Field-level (``fetch_fields``) caching keeps its existing per-call shape
because the API is column-scoped rather than range-scoped.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/ohlcv")
STALE_AFTER_HOURS = 12          # mutable-tail refresh window
HISTORY_FREEZE_DAYS = 7         # data older than this is immutable

_DATE_FMT = "%Y-%m-%d"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_")


class CachedDataPlugin(DataPlugin):
    """Wraps any DataPlugin with a range-aware parquet cache."""

    def __init__(
        self,
        inner: DataPlugin,
        cache_dir: Path = CACHE_DIR,
        stale_hours: float = STALE_AFTER_HOURS,
        freeze_days: int = HISTORY_FREEZE_DAYS,
    ):
        self._inner = inner
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._stale_hours = stale_hours
        self._freeze_days = freeze_days

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._inner.name

    # ── Path helpers ──

    def _ohlcv_path(self, symbol: str, freq: str) -> Path:
        return self._cache_dir / freq / f"{_safe_symbol(symbol)}.parquet"

    def _is_mtime_stale(self, path: Path) -> bool:
        if not path.exists():
            return True
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return (datetime.now() - mtime) >= timedelta(hours=self._stale_hours)

    # ── Read / write ──

    @staticmethod
    def _strip_tz(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
        """Drop timezone info, keeping wall-clock dates.

        OHLCV daily bars are date-keyed, not time-of-day. Mixing tz-aware
        (from crypto/FX feeds) and tz-naive (from stock feeds) indexes in
        the same cache file would error on every comparison or slice. By
        stripping tz at the boundary, all cache logic works on naive
        Timestamps and stays consistent.
        """
        if getattr(idx, "tz", None) is not None:
            return idx.tz_localize(None)
        return idx

    @staticmethod
    def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
        """Return ``df`` with a tz-naive sorted DatetimeIndex."""
        if df.empty:
            return df
        idx = pd.to_datetime(df.index)
        idx = CachedDataPlugin._strip_tz(idx)
        df = df.copy()
        df.index = idx
        return df.sort_index()

    @classmethod
    def _read_existing(cls, path: Path) -> pd.DataFrame | None:
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
        except Exception:
            logger.warning("Corrupt parquet %s; treating as empty", path.name)
            return None
        return cls._normalize_frame(df)

    @staticmethod
    def _save_atomic(df: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".parquet.tmp")
        try:
            df.to_parquet(tmp)
            tmp.replace(path)
        except Exception:
            logger.warning("Failed to write cache %s", path.name)
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    # ── Range logic ──

    def _missing_ranges(
        self,
        existing: pd.DataFrame | None,
        start: pd.Timestamp,
        end: pd.Timestamp,
        path: Path,
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """Return the (start, end) ranges that need fetching from upstream.

        Empty list = full cache hit, return slice without any network call.
        """
        today = pd.Timestamp.now().normalize()
        freeze_cutoff = today - pd.Timedelta(days=self._freeze_days)

        if existing is None or existing.empty:
            return [(start, end)]

        ex_start = existing.index.min().normalize()
        ex_end = existing.index.max().normalize()

        gaps: list[tuple[pd.Timestamp, pd.Timestamp]] = []

        # Gap BEFORE existing: only if requested start predates cache.
        if start < ex_start:
            gaps.append((start, ex_start - pd.Timedelta(days=1)))

        # Gap AFTER existing: only if requested end overshoots cache.
        if end > ex_end:
            gaps.append((ex_end + pd.Timedelta(days=1), end))

        # Mutable-tail refresh: recent data may have been corrected upstream.
        # Only triggers when the request actually reaches into the unfrozen
        # window AND the cache file is stale by mtime. Old historical
        # requests (end < freeze_cutoff) never trigger this path.
        if end > freeze_cutoff and self._is_mtime_stale(path):
            refresh_start = max(start, freeze_cutoff)
            refresh_end = end
            if refresh_start <= refresh_end:
                gaps.append((refresh_start, refresh_end))

        return gaps

    # ── Public API ──

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        path = self._ohlcv_path(symbol, freq)
        existing = self._read_existing(path)

        try:
            start_ts = pd.Timestamp(start).normalize()
            end_ts = pd.Timestamp(end).normalize()
        except (ValueError, TypeError):
            logger.warning("Invalid date range for %s: %r..%r", symbol, start, end)
            return self._inner.fetch_ohlcv(symbol, start, end, freq)

        if start_ts > end_ts:
            return pd.DataFrame()

        gaps = self._missing_ranges(existing, start_ts, end_ts, path)

        if not gaps:
            logger.debug("Cache hit (full): %s [%s..%s]", symbol, start, end)
            return existing.loc[start_ts:end_ts] if existing is not None else pd.DataFrame()

        new_frames: list[pd.DataFrame] = []
        for gap_start, gap_end in gaps:
            if gap_start > gap_end:
                continue
            logger.debug(
                "Cache miss: %s [%s..%s] from %s",
                symbol, gap_start.strftime(_DATE_FMT), gap_end.strftime(_DATE_FMT), self._inner.name,
            )
            try:
                fetched = self._inner.fetch_ohlcv(
                    symbol,
                    gap_start.strftime(_DATE_FMT),
                    gap_end.strftime(_DATE_FMT),
                    freq,
                )
            except Exception as exc:
                logger.debug("Upstream fetch failed for %s: %s", symbol, exc)
                continue
            if fetched is None or fetched.empty:
                continue
            # Normalize tz before mixing with cached data — feeds that return
            # tz-aware indexes (crypto/FX) would otherwise poison cache slices.
            new_frames.append(self._normalize_frame(fetched))

        if new_frames:
            pieces = ([existing] if existing is not None and not existing.empty else []) + new_frames
            combined = pd.concat(pieces)
            # Dedupe on index; keep the most recent (last) write so refreshed
            # mutable-tail rows replace older versions.
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            self._save_atomic(combined, path)
            existing = combined

        if existing is None or existing.empty:
            return pd.DataFrame()
        return existing.loc[start_ts:end_ts]

    def fetch_fundamentals(self, symbol: str) -> dict:
        return self._inner.fetch_fundamentals(symbol)

    def available_fields(self) -> dict[str, list[str]]:
        return self._inner.available_fields()

    def field_history_modes(self) -> dict[str, str]:
        return self._inner.field_history_modes()

    def history_probe_start(self, freq: str = "1d") -> str:
        return self._inner.history_probe_start(freq)

    def fetch_fields(self, symbol: str, fields: list[str],
                     start: str = "", end: str = "") -> pd.DataFrame:
        # Field caches are per-call (column-scoped) — kept simple. They share
        # the same staleness rule for consistency.
        fields_key = ",".join(sorted(fields))
        key = f"fields_{symbol}_{start}_{end}_{fields_key}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:12]
        path = self._cache_dir / "fields" / f"{_safe_symbol(symbol)}_{digest}.parquet"

        if path.exists() and not self._is_mtime_stale(path):
            try:
                return pd.read_parquet(path)
            except Exception:
                logger.warning("Failed to read fields cache %s, refetching", path.name)

        df = self._inner.fetch_fields(symbol, fields, start, end)

        if df is not None and not df.empty:
            self._save_atomic(df, path)

        return df

    def cached_inventory(self) -> dict[str, dict]:
        """Scan the cache and return per-symbol coverage.

        Returns ``{symbol: {start, end, rows, freq, fresh, path}}`` for each
        cached series. With the range-aware layout this is a cheap directory
        walk: one file per (symbol, freq).
        """
        inventory: dict[str, dict] = {}
        if not self._cache_dir.exists():
            return inventory

        for freq_dir in self._cache_dir.iterdir():
            if not freq_dir.is_dir() or freq_dir.name == "fields":
                continue
            freq = freq_dir.name
            for path in freq_dir.glob("*.parquet"):
                symbol = path.stem
                try:
                    df = pd.read_parquet(path, columns=["close"])
                except Exception:
                    continue
                if df.empty:
                    continue
                idx = pd.to_datetime(df.index)
                start = idx.min().strftime(_DATE_FMT)
                end = idx.max().strftime(_DATE_FMT)
                fresh = not self._is_mtime_stale(path)
                inventory[symbol] = {
                    "start": start,
                    "end": end,
                    "rows": int(len(df)),
                    "freq": freq,
                    "fresh": fresh,
                    "path": str(path),
                }

        return inventory

    def list_symbols(self) -> list[str]:
        return self._inner.list_symbols()

    def validate_key(self) -> bool:
        return self._inner.validate_key()
