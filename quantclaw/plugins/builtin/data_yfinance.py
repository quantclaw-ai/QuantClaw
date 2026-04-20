"""yfinance data plugin -- free, no API key needed.

Supports OHLCV, fundamentals, sentiment, and technical anchor fields.
All fields are fetchable individually via fetch_fields() or as categories.
"""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

# Field registry: category -> list of field names
FIELD_CATALOG: dict[str, list[str]] = {
    "ohlcv": ["open", "high", "low", "close", "volume"],
    "fundamentals": [
        "trailingPE", "forwardPE", "priceToBook",
        "profitMargins", "operatingMargins", "returnOnEquity",
        "revenueGrowth", "earningsGrowth",
        "currentRatio", "debtToEquity", "freeCashflow",
        "enterpriseToRevenue", "enterpriseToEbitda",
        "dividendYield", "payoutRatio",
    ],
    "sentiment": [
        "shortRatio", "shortPercentOfFloat",
        "heldPercentInsiders", "heldPercentInstitutions",
    ],
    "technical": [
        "beta",
        "fiftyDayAverage", "twoHundredDayAverage",
        "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
        "averageVolume", "averageVolume10days",
        "marketCap", "enterpriseValue",
    ],
}

# Flat lookup: field_name -> category
_FIELD_TO_CATEGORY: dict[str, str] = {
    field: cat for cat, fields in FIELD_CATALOG.items() for field in fields
}


class YFinanceDataPlugin(DataPlugin):
    name = "data_yfinance"

    def fetch_ohlcv(self, symbol: str, start: str, end: str, freq: str = "1d") -> pd.DataFrame:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        interval = "1d" if freq == "1d" else "1m"
        df = ticker.history(start=start, end=end, interval=interval)
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        return {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "name": info.get("shortName"),
        }

    def available_fields(self) -> dict[str, list[str]]:
        return dict(FIELD_CATALOG)

    def field_history_modes(self) -> dict[str, str]:
        modes = {field: "time_series" for field in FIELD_CATALOG["ohlcv"]}
        for category in ("fundamentals", "sentiment", "technical"):
            for field in FIELD_CATALOG[category]:
                modes[field] = "snapshot"
        return modes

    def fetch_fields(self, symbol: str, fields: list[str],
                     start: str = "", end: str = "") -> pd.DataFrame:
        """Fetch specific fields and return as a DataFrame.

        OHLCV fields return time-series data indexed by date.
        Fundamental/sentiment/technical fields are scalar snapshots
        broadcast across the OHLCV date index.
        """
        import yfinance as yf

        ticker = yf.Ticker(symbol)

        # Determine which categories we need
        need_ohlcv = any(_FIELD_TO_CATEGORY.get(f) == "ohlcv" for f in fields)
        need_info = any(_FIELD_TO_CATEGORY.get(f) in ("fundamentals", "sentiment", "technical")
                        for f in fields)

        result = pd.DataFrame()

        # Fetch OHLCV base if needed (or if we need a date index for scalars)
        if need_ohlcv or need_info:
            s = start or "2023-01-01"
            e = end or "2024-12-31"
            df = self.fetch_ohlcv(symbol, s, e)
            if df.empty:
                return pd.DataFrame()

            if need_ohlcv:
                ohlcv_fields = [f for f in fields if _FIELD_TO_CATEGORY.get(f) == "ohlcv"]
                available = [f for f in ohlcv_fields if f in df.columns]
                result = df[available].copy() if available else df[[]].copy()
            else:
                # We still need the date index for broadcasting scalars
                result = df[[]].copy()

        # Fetch info-based fields (scalar, broadcast across dates)
        if need_info:
            try:
                info = ticker.info or {}
            except Exception:
                logger.warning("Failed to fetch info for %s", symbol)
                info = {}

            for f in fields:
                cat = _FIELD_TO_CATEGORY.get(f)
                if cat in ("fundamentals", "sentiment", "technical"):
                    val = info.get(f)
                    if val is not None and not result.empty:
                        result[f] = float(val)

        return result

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS", "BAC", "XOM",
            "CSCO", "PFE", "INTC", "VZ", "KO", "PEP", "MRK", "ABT", "NKE",
            "CVX", "CRM", "AMD", "QCOM", "TXN", "COST", "LOW", "CAT",
        ]

    def validate_key(self) -> bool:
        return True
