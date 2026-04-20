"""Tiingo data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


class TiingoDataPlugin(DataPlugin):
    name = "data_tiingo"

    def __init__(self):
        self._key = os.environ.get("TIINGO_API_KEY", "")
        self._last_call = 0.0

    def _throttle(self):
        delay = 0.15  # conservative spacing
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

    def _headers(self) -> dict:
        return {
            "Authorization": f"Token {self._key}",
            "Content-Type": "application/json",
        }

    def _get(self, url: str, params: dict | None = None) -> list | dict:
        self._throttle()
        try:
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Tiingo API error (%s): %s", url, exc)
            return {}

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
        params: dict = {}
        if start:
            params["startDate"] = start
        if end:
            params["endDate"] = end

        data = self._get(url, params)
        if not isinstance(data, list) or not data:
            return pd.DataFrame()

        rows = []
        for rec in data:
            rows.append({
                "date": rec.get("date", ""),
                "open": self._safe_float(rec.get("adjOpen", rec.get("open"))),
                "high": self._safe_float(rec.get("adjHigh", rec.get("high"))),
                "low": self._safe_float(rec.get("adjLow", rec.get("low"))),
                "close": self._safe_float(
                    rec.get("adjClose", rec.get("close"))),
                "volume": self._safe_float(
                    rec.get("adjVolume", rec.get("volume"))),
            })

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}"
        data = self._get(url)
        if not isinstance(data, dict):
            return {}
        return {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "exchange": data.get("exchangeCode", ""),
            "start_date": data.get("startDate", ""),
            "end_date": data.get("endDate", ""),
        }

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS",
        ]

    def validate_key(self) -> bool:
        if not self._key:
            return False
        url = "https://api.tiingo.com/tiingo/daily/AAPL"
        data = self._get(url)
        return isinstance(data, dict) and bool(data.get("name"))
