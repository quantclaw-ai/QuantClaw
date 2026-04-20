"""Nasdaq Data Link (Quandl) data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


class NasdaqDataPlugin(DataPlugin):
    name = "data_nasdaq"

    def __init__(self):
        self._key = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "")
        self._rate_limit = 30  # ~300 req/10s
        self._last_call = 0.0

    def _throttle(self):
        delay = 1.0 / self._rate_limit
        elapsed = time.time() - self._last_call
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_call = time.time()

    def _safe_float(self, val, default=0.0):
        if val is None or val == "" or val == "-":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _get(self, database_code: str, dataset_code: str,
             start: str = "", end: str = "") -> dict:
        self._throttle()
        url = (
            f"https://data.nasdaq.com/api/v3/datasets/"
            f"{database_code}/{dataset_code}.json"
        )
        params: dict = {"api_key": self._key}
        if start:
            params["start_date"] = start
        if end:
            params["end_date"] = end
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Nasdaq API error for %s/%s: %s",
                           database_code, dataset_code, exc)
            return {}

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        parts = symbol.split("/", 1)
        if len(parts) != 2:
            logger.warning("Symbol must be database/dataset format: %s", symbol)
            return pd.DataFrame()

        data = self._get(parts[0], parts[1], start, end)
        dataset = data.get("dataset", {})
        columns = [c.lower() for c in dataset.get("column_names", [])]
        rows = dataset.get("data", [])
        if not rows or not columns:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=columns)

        # Find date column
        date_col = next((c for c in columns if "date" in c), columns[0])
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col).sort_index()
        df.index.name = "date"

        # Map to OHLCV if columns exist, otherwise treat as single-value
        col_map = {}
        for target, candidates in [
            ("open", ["open", "adj. open"]),
            ("high", ["high", "adj. high"]),
            ("low", ["low", "adj. low"]),
            ("close", ["close", "adj. close", "value", "settle"]),
            ("volume", ["volume", "adj. volume"]),
        ]:
            for c in candidates:
                if c in df.columns:
                    col_map[target] = c
                    break

        if "close" not in col_map:
            # Use first numeric column as close
            for c in df.columns:
                try:
                    pd.to_numeric(df[c])
                    col_map["close"] = c
                    break
                except (ValueError, TypeError):
                    continue

        if "close" not in col_map:
            return pd.DataFrame()

        result = pd.DataFrame(index=df.index)
        close_col = col_map["close"]
        result["close"] = df[close_col].apply(self._safe_float)
        result["open"] = df[col_map.get("open", close_col)].apply(self._safe_float)
        result["high"] = df[col_map.get("high", close_col)].apply(self._safe_float)
        result["low"] = df[col_map.get("low", close_col)].apply(self._safe_float)
        result["volume"] = (
            df[col_map["volume"]].apply(self._safe_float)
            if "volume" in col_map else 0
        )
        return result[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        parts = symbol.split("/", 1)
        if len(parts) != 2:
            return {}
        data = self._get(parts[0], parts[1])
        dataset = data.get("dataset", {})
        return {
            "name": dataset.get("name", ""),
            "description": dataset.get("description", ""),
            "frequency": dataset.get("frequency", ""),
            "database_code": dataset.get("database_code", ""),
        }

    def list_symbols(self) -> list[str]:
        return [
            "WIKI/AAPL", "WIKI/MSFT", "FRED/GDP", "FRED/UNRATE",
            "LBMA/GOLD", "ODA/PALUM_USD",
        ]

    def validate_key(self) -> bool:
        if not self._key:
            return False
        data = self._get("WIKI", "AAPL", start="2024-01-01", end="2024-01-05")
        return bool(data.get("dataset", {}).get("data"))
