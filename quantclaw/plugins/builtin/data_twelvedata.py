"""Twelve Data data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


class TwelveDataPlugin(DataPlugin):
    name = "data_twelvedata"

    def __init__(self):
        self._key = os.environ.get("TWELVE_DATA_API_KEY", "")
        self._rate_limit = 8  # 8 req/min free tier
        self._last_call = 0.0

    def _throttle(self):
        delay = 60.0 / self._rate_limit
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

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self._throttle()
        url = f"https://api.twelvedata.com/{endpoint}"
        all_params = {"apikey": self._key}
        if params:
            all_params.update(params)
        try:
            resp = requests.get(url, params=all_params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Twelve Data API error (%s): %s", endpoint, exc)
            return {}

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        interval_map = {"1d": "1day", "1h": "1h", "1m": "1min"}
        interval = interval_map.get(freq, "1day")
        data = self._get("time_series", {
            "symbol": symbol,
            "interval": interval,
            "start_date": start,
            "end_date": end,
            "outputsize": 5000,
        })
        values = data.get("values", [])
        if not values:
            return pd.DataFrame()

        rows = []
        for v in values:
            rows.append({
                "date": v.get("datetime", ""),
                "open": self._safe_float(v.get("open")),
                "high": self._safe_float(v.get("high")),
                "low": self._safe_float(v.get("low")),
                "close": self._safe_float(v.get("close")),
                "volume": self._safe_float(v.get("volume")),
            })

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        data = self._get("statistics", {"symbol": symbol})
        stats = data.get("statistics", {})
        valuations = stats.get("valuations", {})
        financials = stats.get("financials", {})
        return {
            "pe_ratio": self._safe_float(valuations.get("trailing_pe")),
            "forward_pe": self._safe_float(valuations.get("forward_pe")),
            "market_cap": self._safe_float(
                valuations.get("market_capitalization")),
            "dividend_yield": self._safe_float(
                financials.get("dividend_yield")),
            "name": data.get("name", ""),
            "exchange": data.get("exchange", ""),
        }

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS",
        ]

    def validate_key(self) -> bool:
        if not self._key:
            return False
        data = self._get("time_series", {
            "symbol": "AAPL", "interval": "1day", "outputsize": 1,
        })
        return "values" in data
