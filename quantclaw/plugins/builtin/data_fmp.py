"""Financial Modeling Prep data plugin -- requires API key (free tier available)."""
from __future__ import annotations

import logging
import os
import time

import pandas as pd
import requests

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


class FMPDataPlugin(DataPlugin):
    name = "data_fmp"

    def __init__(self):
        self._key = os.environ.get("FMP_API_KEY", "")
        self._rate_limit = 5  # conservative for 250/day free tier
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

    def _get(self, path: str, params: dict | None = None) -> list | dict:
        self._throttle()
        url = f"https://financialmodelingprep.com/api/v3/{path}"
        all_params = {"apikey": self._key}
        if params:
            all_params.update(params)
        try:
            resp = requests.get(url, params=all_params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("FMP API error (%s): %s", path, exc)
            return {}

    def fetch_ohlcv(self, symbol: str, start: str, end: str,
                    freq: str = "1d") -> pd.DataFrame:
        params: dict = {}
        if start:
            params["from"] = start
        if end:
            params["to"] = end

        data = self._get(f"historical-price-full/{symbol}", params)
        if isinstance(data, dict):
            records = data.get("historical", [])
        else:
            records = []
        if not records:
            return pd.DataFrame()

        rows = []
        for rec in records:
            rows.append({
                "date": rec.get("date", ""),
                "open": self._safe_float(rec.get("open")),
                "high": self._safe_float(rec.get("high")),
                "low": self._safe_float(rec.get("low")),
                "close": self._safe_float(rec.get("close")),
                "volume": self._safe_float(rec.get("volume")),
            })

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        profile_data = self._get(f"profile/{symbol}")
        profile = profile_data[0] if isinstance(profile_data, list) and profile_data else {}
        metrics_data = self._get(f"key-metrics/{symbol}", {
            "period": "annual", "limit": "5",
        })
        latest_metrics = (
            metrics_data[0]
            if isinstance(metrics_data, list) and metrics_data else {}
        )
        return {
            "name": profile.get("companyName", ""),
            "market_cap": self._safe_float(profile.get("mktCap")),
            "pe_ratio": self._safe_float(profile.get("peRatio")),  # noqa: ERA001
            "sector": profile.get("sector", ""),
            "industry": profile.get("industry", ""),
            "exchange": profile.get("exchange", ""),
            "revenue_per_share": self._safe_float(
                latest_metrics.get("revenuePerShare")),
            "net_income_per_share": self._safe_float(
                latest_metrics.get("netIncomePerShare")),
            "debt_to_equity": self._safe_float(
                latest_metrics.get("debtToEquity")),
            "current_ratio": self._safe_float(
                latest_metrics.get("currentRatio")),
        }

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "ohlcv": ["open", "high", "low", "close", "volume"],
            "fundamentals": [
                "peRatio", "marketCap", "revenuePerShare",
                "netIncomePerShare", "debtToEquity", "currentRatio",
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
        data = self._get("profile/AAPL")
        return isinstance(data, list) and len(data) > 0
