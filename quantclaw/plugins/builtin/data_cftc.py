"""CFTC Commitments of Traders data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

COT_API = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json"

# Key futures contracts by CFTC market code
DEFAULT_CONTRACTS: dict[str, str] = {
    # Equity indices
    "098662": "E-mini S&P 500",
    "099741": "E-mini Nasdaq 100",
    "124603": "E-mini Dow Jones",
    "239742": "E-mini Russell 2000",
    "1170E1": "VIX Futures",
    # Currencies
    "088691": "Euro FX",
    "089741": "Japanese Yen",
    "090741": "British Pound",
    "092741": "Swiss Franc",
    "095741": "Canadian Dollar",
    "091741": "Australian Dollar",
    "102741": "Mexican Peso",
    # Treasuries & rates
    "044601": "U.S. Treasury Bonds",
    "043602": "10-Year T-Note",
    "042601": "5-Year T-Note",
    "041591": "2-Year T-Note",
    "045601": "30-Day Fed Funds",
    # Energy
    "023651": "Crude Oil WTI",
    "067653": "Crude Oil Brent",
    "023391": "Natural Gas Henry Hub",
    "022651": "Heating Oil / ULSD",
    "111416": "RBOB Gasoline",
    # Metals
    "096742": "Gold",
    "084691": "Silver",
    "085692": "Copper",
    "076651": "Platinum",
    # Agriculture
    "001602": "Wheat",
    "002602": "Corn",
    "005602": "Soybeans",
    "073732": "Cotton",
    "080732": "Sugar",
    "083731": "Coffee",
    "040701": "Live Cattle",
}


class CftcDataPlugin(DataPlugin):
    name = "data_cftc"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        params = {
            "$where": f"cftc_contract_market_code='{symbol}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "500",
        }
        try:
            resp = requests.get(COT_API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("CFTC request failed for code %s", symbol)
            return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        rows = []
        for rec in data:
            date_str = rec.get("report_date_as_yyyy_mm_dd")
            if not date_str:
                continue
            try:
                long_pos = float(rec.get("noncomm_positions_long_all", 0))
                short_pos = float(rec.get("noncomm_positions_short_all", 0))
                oi = float(rec.get("open_interest_all", 0))
            except (TypeError, ValueError):
                continue
            net = long_pos - short_pos
            rows.append({
                "date": pd.Timestamp(date_str),
                "open": long_pos,
                "high": long_pos,
                "low": short_pos,
                "close": net,
                "volume": oi,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index("date").sort_index()

        if start:
            df = df.loc[start:]
        if end:
            df = df.loc[:end]

        return df[["open", "high", "low", "close", "volume"]]

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {
            "contract_code": symbol,
            "source": "CFTC COT",
            "type": "positioning",
        }

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "positioning": [
                "commercial_long", "commercial_short",
                "noncommercial_long", "noncommercial_short",
                "total_open_interest",
            ],
        }

    def list_symbols(self) -> list[str]:
        return list(DEFAULT_CONTRACTS.keys())

    def validate_key(self) -> bool:
        return True
