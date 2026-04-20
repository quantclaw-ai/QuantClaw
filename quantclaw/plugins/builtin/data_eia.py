"""U.S. Energy Information Administration data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


class EIADataPlugin(DataPlugin):
    name = "data_eia"

    def __init__(self):
        self._key = os.environ.get("EIA_API_KEY", "")
        self._last_call = 0.0

    def _throttle(self):
        delay = 0.2  # conservative for free tier
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

    def _get(self, route: str, start: str = "", end: str = "") -> dict:
        self._throttle()
        url = f"https://api.eia.gov/v2/{route}"
        params: dict = {
            "api_key": self._key,
            "frequency": "monthly",
            "data[0]": "value",
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
        }
        if start:
            params["start"] = start[:7]  # YYYY-MM
        if end:
            params["end"] = end[:7]
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("EIA API error (%s): %s", route, exc)
            return {}

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        data = self._get(symbol, start, end)
        response = data.get("response", {})
        records = response.get("data", [])
        if not records:
            return pd.DataFrame()

        rows = []
        for rec in records:
            period = rec.get("period", "")
            value = self._safe_float(rec.get("value"))
            if not period:
                continue
            rows.append({
                "date": period,
                "open": value,
                "high": value,
                "low": value,
                "close": value,
                "volume": 0,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        data = self._get(symbol)
        response = data.get("response", {})
        records = response.get("data", [])
        if not records:
            return {}
        latest = records[-1] if records else {}
        return {
            "series": symbol,
            "latest_period": latest.get("period", ""),
            "latest_value": self._safe_float(latest.get("value")),
            "unit": latest.get("unit", ""),
            "description": latest.get("seriesDescription", ""),
        }

    def list_symbols(self) -> list[str]:
        return [
            "petroleum/pri/spt/data",
            "natural-gas/pri/sum/data",
            "electricity/retail-sales/data",
            "total-energy/data",
            "petroleum/stoc/wstk/data",
            "coal/shipments/data",
        ]

    def validate_key(self) -> bool:
        if not self._key:
            return False
        data = self._get("petroleum/pri/spt/data",
                         start="2024-01", end="2024-02")
        return bool(data.get("response", {}).get("data"))
