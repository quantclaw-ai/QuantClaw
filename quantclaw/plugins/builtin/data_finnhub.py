"""Finnhub data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


class FinnhubDataPlugin(DataPlugin):
    name = "data_finnhub"

    def __init__(self):
        self._key = os.environ.get("FINNHUB_API_KEY", "")
        self._rate_limit = 60  # 60 req/min free tier
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
        url = f"https://finnhub.io/api/v1/{endpoint}"
        all_params = {"token": self._key}
        if params:
            all_params.update(params)
        try:
            resp = requests.get(url, params=all_params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Finnhub API error (%s): %s", endpoint, exc)
            return {}

    def _to_unix(self, date_str: str) -> int:
        return int(datetime.strptime(date_str[:10], "%Y-%m-%d").timestamp())

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        resolution_map = {"1d": "D", "1h": "60", "1m": "1"}
        resolution = resolution_map.get(freq, "D")
        data = self._get("stock/candle", {
            "symbol": symbol,
            "resolution": resolution,
            "from": self._to_unix(start),
            "to": self._to_unix(end),
        })
        if data.get("s") != "ok" or "c" not in data:
            return pd.DataFrame()

        timestamps = data.get("t", [])
        df = pd.DataFrame({
            "date": pd.to_datetime(timestamps, unit="s"),
            "open": [self._safe_float(v) for v in data.get("o", [])],
            "high": [self._safe_float(v) for v in data.get("h", [])],
            "low": [self._safe_float(v) for v in data.get("l", [])],
            "close": [self._safe_float(v) for v in data.get("c", [])],
            "volume": [self._safe_float(v) for v in data.get("v", [])],
        })
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        profile = self._get("stock/profile2", {"symbol": symbol})
        earnings = self._get("stock/earnings", {"symbol": symbol})
        latest_earning = earnings[0] if isinstance(earnings, list) and earnings else {}
        return {
            "name": profile.get("name", ""),
            "market_cap": self._safe_float(profile.get("marketCapitalization")),
            "shares_outstanding": self._safe_float(
                profile.get("shareOutstanding")),
            "industry": profile.get("finnhubIndustry", ""),
            "exchange": profile.get("exchange", ""),
            "ipo_date": profile.get("ipo", ""),
            "latest_eps_actual": self._safe_float(
                latest_earning.get("actual")),
            "latest_eps_estimate": self._safe_float(
                latest_earning.get("estimate")),
        }

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "fundamentals": [
                "marketCapitalization", "shareOutstanding", "peRatio",
            ],
            "sentiment": [
                "insider_sentiment_mspr", "insider_sentiment_change",
            ],
        }

    def fetch_fields(self, symbol: str, fields: list[str],
                     start: str = "", end: str = "") -> pd.DataFrame:
        sentiment_fields = {"insider_sentiment_mspr", "insider_sentiment_change"}
        needed = sentiment_fields & set(fields)
        if not needed:
            return pd.DataFrame()

        params: dict = {"symbol": symbol}
        if start:
            params["from"] = start[:10]
        if end:
            params["to"] = end[:10]
        data = self._get("stock/insider-sentiment", params)
        records = data.get("data", [])
        if not records:
            return pd.DataFrame()

        rows = []
        for rec in records:
            row: dict = {"date": f"{rec.get('year', 2024)}-{rec.get('month', 1):02d}-01"}
            if "insider_sentiment_mspr" in needed:
                row["insider_sentiment_mspr"] = self._safe_float(rec.get("mspr"))
            if "insider_sentiment_change" in needed:
                row["insider_sentiment_change"] = self._safe_float(rec.get("change"))
            rows.append(row)

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS",
        ]

    def validate_key(self) -> bool:
        if not self._key:
            return False
        data = self._get("stock/profile2", {"symbol": "AAPL"})
        return bool(data.get("name"))
