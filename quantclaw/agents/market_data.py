"""Shared market-data loading helpers for agent pipelines."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

BASE_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
# Use a recent default so callers that don't specify ``start`` still get
# a useful backtest window. 1970-01-01 was previously used, which made
# yfinance log "no data before listing date" warnings for every modern
# ticker (AAPL listed 1980, GOOG 2004, etc.) — pure noise that masked
# actual data-fetch failures in the logs.
DEFAULT_HISTORY_START = "2015-01-01"
TIME_SERIES_FIELD_MODE = "time_series"
SNAPSHOT_FIELD_MODE = "snapshot"
_OHLCV_PLUGIN_NAMES = (
    "data_yfinance",
    "data_stooq",
    "data_alphavantage",
    "data_twelvedata",
    "data_finnhub",
    "data_tiingo",
    "data_fmp",
    "data_simfin",
    "data_nasdaq",
)
_COLUMN_PATTERNS = (
    re.compile(r"df\[['\"]([^'\"]+)['\"]\]"),
    re.compile(r'df\["([^"]+)"\]'),
    re.compile(r"df\['([^']+)'\]"),
)


@dataclass
class MarketDataBundle:
    frames: dict[str, Any]
    metadata: dict[str, dict]
    availability: dict[str, Any] = field(default_factory=dict)


def extract_required_columns_from_code(code: str) -> list[str]:
    """Best-effort extraction of DataFrame column references from Python code."""
    if not code:
        return []
    columns: list[str] = []
    seen: set[str] = set()
    for pattern in _COLUMN_PATTERNS:
        for match in pattern.findall(code):
            if match not in seen:
                seen.add(match)
                columns.append(match)
    return columns


def extra_fields_from_columns(columns: list[str]) -> list[str]:
    base = set(BASE_OHLCV_COLUMNS)
    return [column for column in columns if column not in base]


def load_market_data(
    config: dict,
    symbols: list[str],
    start: str | None,
    end: str | None,
    *,
    extra_fields: list[str] | None = None,
) -> MarketDataBundle:
    """Fetch market data with dynamic history discovery and field enrichment.

    When ``start`` is omitted, the loader probes each provider for the deepest
    available history and selects the source that offers the best combination of
    recent coverage and lookback depth for each symbol.
    """
    from quantclaw.plugins.manager import PluginManager

    if not symbols:
        return MarketDataBundle(frames={}, metadata={}, availability={})

    requested_start = _normalize_start(start)
    requested_end = _normalize_end(end)
    requested_end_ts = pd.Timestamp(requested_end)

    data_plugin_names = config.get("plugins", {}).get("data", ["data_yfinance"])
    if isinstance(data_plugin_names, str):
        data_plugin_names = [data_plugin_names]

    ohlcv_plugin_names = [name for name in data_plugin_names if name in _OHLCV_PLUGIN_NAMES]
    if not ohlcv_plugin_names:
        ohlcv_plugin_names = ["data_yfinance"]

    pm = PluginManager()
    pm.discover()

    price_plugins: list[tuple[int, str, Any]] = []
    for priority, plugin_name in enumerate(ohlcv_plugin_names):
        plugin = pm.get("data", plugin_name)
        if plugin is not None:
            price_plugins.append((priority, plugin_name, plugin))

    field_plugins: list[tuple[int, str, Any]] = []
    for priority, plugin_name in enumerate(data_plugin_names):
        plugin = pm.get("data", plugin_name)
        if plugin is not None:
            field_plugins.append((priority, plugin_name, plugin))

    if not price_plugins:
        return MarketDataBundle(
            frames={},
            metadata={"error": f"No data plugins found from: {ohlcv_plugin_names}"},
            availability={},
        )

    requested_extra_fields = [
        field_name for field_name in (extra_fields or [])
        if field_name not in BASE_OHLCV_COLUMNS
    ]

    frames: dict[str, Any] = {}
    metadata: dict[str, dict] = {}
    availability_symbols: dict[str, dict[str, Any]] = {}

    for symbol in symbols:
        price_candidates: list[dict[str, Any]] = []
        price_frames: dict[str, pd.DataFrame] = {}
        last_error = "No data returned from any plugin"

        for priority, plugin_name, plugin in price_plugins:
            probe_start = requested_start or plugin.history_probe_start("1d") or DEFAULT_HISTORY_START
            try:
                df = plugin.fetch_ohlcv(symbol, probe_start, requested_end)
            except Exception as exc:
                last_error = str(exc) or f"{plugin_name} fetch failed"
                logger.debug("Plugin %s failed for %s, trying next", plugin_name, symbol)
                continue

            df = _prepare_frame(df)
            if df is None or df.empty:
                last_error = f"No data returned from {plugin_name}"
                continue

            price_frames[plugin_name] = df
            candidate = _summarize_frame(df, plugin_name)
            candidate["_priority"] = priority
            price_candidates.append(candidate)

        if not price_candidates:
            metadata[symbol] = {"error": last_error}
            availability_symbols[symbol] = {
                "price": None,
                "price_candidates": [],
                "fields": {},
                "field_candidates": {},
                "error": last_error,
            }
            continue

        selected_price = _select_best_candidate(price_candidates, requested_end_ts)
        selected_source = str(selected_price["source"])
        base_df = price_frames[selected_source].copy()

        field_candidates: dict[str, list[dict[str, Any]]] = {}
        field_frames: dict[str, dict[str, pd.DataFrame]] = {}
        selected_fields: dict[str, dict[str, Any]] = {}

        if requested_extra_fields:
            for priority, plugin_name, plugin in field_plugins:
                valid_fields = [field_name for field_name in requested_extra_fields if _plugin_supports_field(plugin, field_name)]
                if not valid_fields:
                    continue

                probe_start = requested_start or plugin.history_probe_start("1d") or DEFAULT_HISTORY_START
                try:
                    extra_df = plugin.fetch_fields(symbol, valid_fields, probe_start, requested_end)
                except Exception:
                    logger.debug("Failed to fetch extra fields from %s for %s", plugin_name, symbol)
                    continue

                extra_df = _prepare_frame(extra_df)
                if extra_df is None or extra_df.empty:
                    continue

                field_frames.setdefault(plugin_name, {})
                modes = plugin.field_history_modes()

                for field_name in valid_fields:
                    if field_name not in extra_df.columns:
                        continue

                    series = extra_df[field_name].dropna()
                    if series.empty:
                        continue

                    mode = modes.get(field_name, TIME_SERIES_FIELD_MODE)
                    candidate = {
                        "source": plugin_name,
                        "start": _format_timestamp(series.index.min()),
                        "end": _format_timestamp(series.index.max()),
                        "rows": int(series.shape[0]),
                        "mode": mode,
                        "_priority": priority,
                    }
                    field_candidates.setdefault(field_name, []).append(candidate)
                    field_frames[plugin_name][field_name] = _prepare_frame(extra_df[[field_name]])

            for field_name in requested_extra_fields:
                candidates = field_candidates.get(field_name, [])
                if not candidates:
                    continue

                time_series_candidates = [
                    candidate for candidate in candidates
                    if candidate.get("mode") != SNAPSHOT_FIELD_MODE
                ]
                ranked_pool = time_series_candidates or candidates
                selected_field = _select_best_candidate(ranked_pool, requested_end_ts)
                selected_fields[field_name] = _strip_private_keys(selected_field)

                join_source = str(selected_field["source"])
                join_df = field_frames.get(join_source, {}).get(field_name)
                if join_df is None or join_df.empty:
                    continue
                base_df = _join_field(base_df, join_df, field_name)

        base_df = _prepare_frame(base_df)
        frames[symbol] = base_df

        symbol_metadata = _summarize_frame(base_df, selected_source)
        symbol_metadata["columns"] = list(base_df.columns)
        if selected_fields:
            symbol_metadata["field_sources"] = {
                field_name: info["source"]
                for field_name, info in selected_fields.items()
            }
            symbol_metadata["field_history"] = {
                field_name: {
                    key: value
                    for key, value in info.items()
                    if key != "source"
                }
                for field_name, info in selected_fields.items()
            }
        metadata[symbol] = symbol_metadata

        availability_symbols[symbol] = {
            "price": _strip_private_keys(selected_price),
            "price_candidates": [_strip_private_keys(candidate) for candidate in price_candidates],
            "fields": selected_fields,
            "field_candidates": {
                field_name: [_strip_private_keys(candidate) for candidate in candidates]
                for field_name, candidates in field_candidates.items()
            },
        }

    availability = _build_availability_summary(
        symbols=symbols,
        requested_start=requested_start,
        requested_end=requested_end,
        requested_extra_fields=requested_extra_fields,
        symbol_coverage=availability_symbols,
    )

    return MarketDataBundle(
        frames=frames,
        metadata=metadata,
        availability=availability,
    )


def _normalize_start(start: str | None) -> str | None:
    if start is None:
        return None
    start_text = str(start).strip()
    return start_text or None


def _normalize_end(end: str | None) -> str:
    if end is None or not str(end).strip():
        return datetime.now(timezone.utc).date().isoformat()
    return str(end).strip()


def _prepare_frame(df: Any) -> pd.DataFrame | None:
    if df is None:
        return None
    if not isinstance(df, pd.DataFrame):
        return None
    if df.empty:
        return df
    frame = df.copy()
    try:
        frame.index = pd.to_datetime(frame.index)
    except Exception:
        return frame
    if frame.index.has_duplicates:
        frame = frame[~frame.index.duplicated(keep="last")]
    return frame.sort_index()


def _summarize_frame(df: pd.DataFrame, source: str) -> dict[str, Any]:
    summary = {
        "rows": int(len(df)),
        "start": _format_timestamp(df.index.min()),
        "end": _format_timestamp(df.index.max()),
        "source": source,
        "columns": list(df.columns),
    }
    if "close" in df.columns:
        try:
            summary["last_close"] = float(df["close"].iloc[-1])
        except Exception:
            summary["last_close"] = 0.0
    else:
        summary["last_close"] = 0.0
    return summary


def _format_timestamp(value: Any) -> str:
    try:
        ts = pd.Timestamp(value)
    except Exception:
        return str(value)
    return ts.date().isoformat()


def _select_best_candidate(candidates: list[dict[str, Any]], requested_end: pd.Timestamp) -> dict[str, Any]:
    return min(candidates, key=lambda candidate: _candidate_sort_key(candidate, requested_end))


def _candidate_sort_key(candidate: dict[str, Any], requested_end: pd.Timestamp) -> tuple[int, int, int, int]:
    end_ts = pd.Timestamp(candidate.get("end", requested_end))
    start_ts = pd.Timestamp(candidate.get("start", requested_end))
    end_gap = max((requested_end.normalize() - end_ts.normalize()).days, 0)
    return (
        end_gap,
        start_ts.toordinal(),
        -int(candidate.get("rows", 0)),
        int(candidate.get("_priority", 1_000_000)),
    )


def _plugin_supports_field(plugin: Any, field_name: str) -> bool:
    try:
        available = plugin.available_fields()
    except Exception:
        return False
    return any(field_name in fields for fields in available.values())


def _join_field(base_df: pd.DataFrame, join_df: pd.DataFrame, field_name: str) -> pd.DataFrame:
    if field_name in base_df.columns:
        return base_df
    prepared = _prepare_frame(join_df)
    if prepared is None or prepared.empty or field_name not in prepared.columns:
        return base_df
    return base_df.join(prepared[[field_name]], how="left")


def _strip_private_keys(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if not key.startswith("_")}


def _build_availability_summary(
    *,
    symbols: list[str],
    requested_start: str | None,
    requested_end: str,
    requested_extra_fields: list[str],
    symbol_coverage: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    price_entries: list[tuple[str, dict[str, Any]]] = []
    field_entries: list[tuple[str, str, dict[str, Any]]] = []
    missing_symbols: list[str] = []

    for symbol in symbols:
        coverage = symbol_coverage.get(symbol, {})
        price_info = coverage.get("price")
        if price_info:
            price_entries.append((symbol, price_info))
        else:
            missing_symbols.append(symbol)

        for field_name, field_info in coverage.get("fields", {}).items():
            field_entries.append((symbol, field_name, field_info))

    price_common_window = _common_window([
        price_info for _, price_info in price_entries
    ])

    time_series_field_infos = [
        field_info for _, _, field_info in field_entries
        if field_info.get("mode") != SNAPSHOT_FIELD_MODE
    ]
    field_common_window = _common_window(time_series_field_infos)

    recommended_start = price_common_window.get("start")
    recommended_end = price_common_window.get("end")

    if field_common_window:
        recommended_start = _max_date_str(recommended_start, field_common_window.get("start"))
        recommended_end = _min_date_str(recommended_end, field_common_window.get("end"))

    limiting_symbols = []
    if price_common_window.get("start"):
        limiting_symbols = sorted(
            symbol for symbol, price_info in price_entries
            if price_info.get("start") == price_common_window["start"]
        )

    limiting_fields = []
    if field_common_window.get("start"):
        limiting_fields = sorted({
            field_name for _, field_name, field_info in field_entries
            if field_info.get("mode") != SNAPSHOT_FIELD_MODE
            and field_info.get("start") == field_common_window["start"]
        })

    fields_missing_by_symbol: dict[str, list[str]] = {}
    for symbol in symbols:
        coverage = symbol_coverage.get(symbol, {})
        available_fields = set(coverage.get("fields", {}).keys())
        missing = [field_name for field_name in requested_extra_fields if field_name not in available_fields]
        if missing:
            fields_missing_by_symbol[symbol] = missing

    per_symbol_windows = {
        symbol: {
            "start": price_info.get("start"),
            "end": price_info.get("end"),
            "rows": price_info.get("rows"),
            "source": price_info.get("source"),
        }
        for symbol, price_info in price_entries
    }

    return {
        "selection_mode": "max_history" if requested_start is None else "requested_window",
        "requested_window": {
            "start": requested_start,
            "end": requested_end,
            "extra_fields": requested_extra_fields,
        },
        "summary": {
            "symbols_with_price": sorted(symbol for symbol, _ in price_entries),
            "missing_symbols": missing_symbols,
            "price_common_window": price_common_window,
            "field_common_window": field_common_window,
            "recommended_common_window": _window_payload(recommended_start, recommended_end),
            "per_symbol_windows": per_symbol_windows,
            "limiting_symbols": limiting_symbols,
            "limiting_fields": limiting_fields,
            "fields_missing_by_symbol": fields_missing_by_symbol,
        },
        "symbols": symbol_coverage,
    }


def _common_window(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {}
    starts = [entry.get("start") for entry in entries if entry.get("start")]
    ends = [entry.get("end") for entry in entries if entry.get("end")]
    if not starts or not ends:
        return {}
    start = max(starts, key=_date_ordinal)
    end = min(ends, key=_date_ordinal)
    return _window_payload(start, end)


def _window_payload(start: str | None, end: str | None) -> dict[str, Any]:
    if not start or not end:
        return {}
    days = max((_date_ordinal(end) - _date_ordinal(start)), 0)
    return {
        "start": start,
        "end": end,
        "days": days,
    }


def _date_ordinal(value: str | None) -> int:
    if not value:
        return 0
    return pd.Timestamp(value).toordinal()


def _max_date_str(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return a if _date_ordinal(a) >= _date_ordinal(b) else b


def _min_date_str(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return a if _date_ordinal(a) <= _date_ordinal(b) else b
