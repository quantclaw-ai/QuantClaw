"""FRED / ALFRED data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

MACRO_SERIES = [
    # GDP & output
    "GDP", "GDPC1", "INDPRO", "TCU", "CPGDPAI",
    # Labor market
    "UNRATE", "PAYEMS", "ICSA", "CCSA", "CIVPART", "JTSJOL", "AWHMAN",
    # Inflation
    "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIFIS",
    # Inflation expectations
    "T5YIE", "T10YIE", "MICH",
    # Yield curve & rates
    "FEDFUNDS", "DFF", "DGS1", "DGS2", "DGS5", "DGS10", "DGS20", "DGS30",
    "T10Y2Y", "T10Y3M", "TB3MS", "DTB3",
    # Credit spreads & financial conditions
    "BAMLH0A0HYM2", "BAMLC0A0CM", "TEDRATE", "STLFSI2", "NFCI",
    # Money supply & Fed balance sheet
    "M1SL", "M2SL", "BOGMBASE", "WALCL", "TOTRESNS",
    # Housing
    "HOUST", "PERMIT", "CSUSHPINSA", "MSPUS", "MORTGAGE30US",
    # Consumer & retail
    "RSXFS", "UMCSENT", "PCE", "DGORDER", "DSPIC96",
    # Commodities & energy
    "DCOILWTICO", "DCOILBRENTEU", "GASREGW", "GOLDAMGBD228NLBM",
    # FX
    "DEXUSEU", "DEXJPUS", "DEXUSUK", "DEXCHUS", "DTWEXBGS",
    # Banking & lending
    "BUSLOANS", "DRCCLACBS", "DRSFRMACBS",
    # Volatility
    "VIXCLS",
]

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredDataPlugin(DataPlugin):
    name = "data_fred"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        try:
            resp = requests.get(
                FRED_CSV_URL,
                params={"id": symbol, "cosd": start, "coed": end},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception:
            logger.warning("FRED fetch failed for %s", symbol)
            return pd.DataFrame()

        try:
            from io import StringIO
            raw = pd.read_csv(StringIO(resp.text))
            # FRED CSV uses "observation_date" or "DATE" as the date column
            date_col = next(
                (c for c in raw.columns if "date" in c.lower()), raw.columns[0],
            )
            raw[date_col] = pd.to_datetime(raw[date_col])
            raw = raw.rename(columns={date_col: "date"}).set_index("date")
            # The value column is named after the series id
            val_col = [c for c in raw.columns if c != "date"]
            if not val_col:
                return pd.DataFrame()
            values = pd.to_numeric(raw[val_col[0]], errors="coerce")
            df = pd.DataFrame({
                "open": values,
                "high": values,
                "low": values,
                "close": values,
                "volume": 0,
            }, index=raw.index)
            df.index.name = "date"
            return df.dropna(subset=["close"])
        except Exception:
            logger.warning("FRED parse failed for %s", symbol)
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {
            "name": symbol,
            "source": "FRED",
            "type": "macro_indicator",
        }

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "macro": ["value"],
            "ohlcv": ["open", "high", "low", "close", "volume"],
        }

    def list_symbols(self) -> list[str]:
        return list(MACRO_SERIES)

    def validate_key(self) -> bool:
        return True
