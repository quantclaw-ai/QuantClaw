"""Alpha Vantage data plugin -- free tier (5 req/min) or premium."""
from __future__ import annotations
import os
import time
import pandas as pd
import requests
from quantclaw.plugins.interfaces import DataPlugin


class AlphaVantageDataPlugin(DataPlugin):
    name = "data_alphavantage"

    def __init__(self):
        self._key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
        self._rate_limit = 5
        self._last_call = 0.0

    def _throttle(self):
        delay = 60 / self._rate_limit
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

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        self._throttle()
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "full",
            "apikey": self._key,
        }
        r = requests.get(
            "https://www.alphavantage.co/query", params=params, timeout=30
        )
        data = r.json()
        ts_key = [k for k in data.keys() if "Time Series" in k]
        if not ts_key:
            return pd.DataFrame()
        rows = []
        for date_str, v in data[ts_key[0]].items():
            rows.append({
                "date": pd.Timestamp(date_str),
                "open": self._safe_float(v.get("1. open")),
                "high": self._safe_float(v.get("2. high")),
                "low": self._safe_float(v.get("3. low")),
                "close": self._safe_float(v.get("4. close")),
                "volume": self._safe_float(v.get("5. volume")),
            })
        df = pd.DataFrame(rows).set_index("date").sort_index()
        return df[(df.index >= start) & (df.index <= end)]

    def fetch_fundamentals(self, symbol: str) -> dict:
        self._throttle()
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "OVERVIEW",
                "symbol": symbol,
                "apikey": self._key,
            },
            timeout=30,
        )
        d = r.json()
        return {
            "pe_ratio": self._safe_float(d.get("TrailingPE")),
            "market_cap": self._safe_float(d.get("MarketCapitalization")),
            "sector": d.get("Sector", ""),
            "name": d.get("Name", ""),
        }

    def list_symbols(self) -> list[str]:
        return []

    def validate_key(self) -> bool:
        if not self._key:
            return False
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_INTRADAY",
                "symbol": "IBM",
                "interval": "5min",
                "apikey": self._key,
            },
            timeout=10,
        )
        return "Error" not in r.text
