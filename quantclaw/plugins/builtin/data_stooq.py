"""Stooq historical data plugin -- free via pandas_datareader.

Falls back to direct CSV if pandas_datareader is unavailable.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)


def _stooq_symbol(symbol: str) -> str:
    """Convert a standard ticker to Stooq URL format."""
    return symbol.lower().replace("^", "").replace("-", ".")


class StooqDataPlugin(DataPlugin):
    name = "data_stooq"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        # Try pandas_datareader first (handles Stooq's anti-bot measures)
        try:
            from pandas_datareader import data as pdr
            df = pdr.DataReader(
                _stooq_symbol(symbol), "stooq",
                start=start, end=end,
            )
            if not df.empty:
                df = df.rename(columns={
                    "Open": "open", "High": "high",
                    "Low": "low", "Close": "close", "Volume": "volume",
                })
                df.index.name = "date"
                expected = ["open", "high", "low", "close", "volume"]
                for col in expected:
                    if col not in df.columns:
                        df[col] = 0.0
                return df[expected].sort_index()
        except ImportError:
            logger.debug("pandas_datareader not installed, trying direct CSV")
        except Exception:
            logger.debug("pandas_datareader stooq fetch failed for %s", symbol)

        # Fallback: direct CSV download
        import requests

        stooq_sym = _stooq_symbol(symbol)
        start_fmt = start.replace("-", "")
        end_fmt = end.replace("-", "")
        url = (
            f"https://stooq.com/q/d/l/?s={stooq_sym}"
            f"&d1={start_fmt}&d2={end_fmt}&i=d"
        )
        try:
            resp = requests.get(
                url, timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (compatible; QuantClaw/1.0)"},
            )
            resp.raise_for_status()
            if "apikey" in resp.text.lower() or "captcha" in resp.text.lower():
                logger.warning("Stooq requires captcha/apikey for %s", symbol)
                return pd.DataFrame()
        except Exception:
            logger.warning("Stooq request failed for %s", symbol)
            return pd.DataFrame()

        try:
            df = pd.read_csv(io.StringIO(resp.text))
        except Exception:
            logger.warning("Failed to parse Stooq CSV for %s", symbol)
            return pd.DataFrame()

        if df.empty or "Date" not in df.columns:
            return pd.DataFrame()

        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        expected = ["open", "high", "low", "close", "volume"]
        for col in expected:
            if col not in df.columns:
                df[col] = 0.0
        return df[expected]

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {"source": "stooq", "note": "Stooq provides OHLCV only"}

    def list_symbols(self) -> list[str]:
        return [
            "SPY", "AAPL", "MSFT", "GOOGL", "AMZN",
            "NVDA", "^SPX", "^DJI", "^NDQ",
        ]

    def validate_key(self) -> bool:
        return True
