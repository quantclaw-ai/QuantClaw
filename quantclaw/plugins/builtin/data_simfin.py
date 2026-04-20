"""SimFin data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

BASE_URL = "https://backend.simfin.com/api/v3"


class SimFinDataPlugin(DataPlugin):
    name = "data_simfin"

    def __init__(self):
        self._key = os.environ.get("SIMFIN_API_KEY", "")
        self._last_call = 0.0

    def _throttle(self):
        delay = 0.5  # conservative for free tier
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

    def _get(self, endpoint: str, params: dict | None = None) -> list | dict:
        self._throttle()
        url = f"{BASE_URL}/{endpoint}"
        all_params = {"api-key": self._key}
        if params:
            all_params.update(params)
        try:
            resp = requests.get(url, params=all_params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("SimFin API error (%s): %s", endpoint, exc)
            return {}

    def _compact_to_dicts(self, data: list | dict) -> list[dict]:
        """Convert SimFin compact format (columns + data) to list of dicts."""
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return []
        columns = item.get("columns", [])
        rows = item.get("data", [])
        return [dict(zip(columns, row)) for row in rows]

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        params: dict = {"ticker": symbol}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        data = self._get("companies/prices/compact", params)
        records = self._compact_to_dicts(data)
        if not records:
            return pd.DataFrame()

        rows = []
        for rec in records:
            date_val = rec.get("Date", rec.get("date", ""))
            if not date_val:
                continue
            rows.append({
                "date": date_val,
                "open": self._safe_float(
                    rec.get("Opening Price", rec.get("Open"))),
                "high": self._safe_float(
                    rec.get("High Price", rec.get("High"))),
                "low": self._safe_float(
                    rec.get("Low Price", rec.get("Low"))),
                "close": self._safe_float(
                    rec.get("Last Closing Price",
                            rec.get("Adj. Close", rec.get("Close")))),
                "volume": self._safe_float(
                    rec.get("Trading Volume", rec.get("Volume"))),
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        data = self._get("companies/statements/compact", {
            "ticker": symbol,
            "statements": "pl,bs,cf",
            "periods": "fy",
            "start": "2020",
            "end": "2025",
        })
        records = self._compact_to_dicts(data)
        if not records:
            return {}
        latest = records[-1]
        return {
            "revenue": self._safe_float(latest.get("Revenue")),
            "net_income": self._safe_float(latest.get("Net Income")),
            "total_assets": self._safe_float(latest.get("Total Assets")),
            "total_liabilities": self._safe_float(
                latest.get("Total Liabilities")),
            "shareholders_equity": self._safe_float(
                latest.get("Shareholders' Equity",
                           latest.get("Total Equity"))),
            "fiscal_year": latest.get("Fiscal Year", ""),
        }

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "fundamentals": [
                "Revenue", "NetIncome", "TotalAssets",
                "TotalLiabilities", "ShareholdersEquity",
            ],
        }

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS",
        ]

    def validate_key(self) -> bool:
        if not self._key:
            return False
        data = self._get("companies/general/compact", {"ticker": "AAPL"})
        records = self._compact_to_dicts(data)
        return len(records) > 0
