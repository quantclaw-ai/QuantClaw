"""Bureau of Labor Statistics data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

BLS_API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"

DEFAULT_SERIES = [
    # Employment
    "CES0000000001",   # Total Nonfarm Payrolls
    "LNS14000000",     # Unemployment Rate (U-3)
    "LNS13327709",     # U-6 Underemployment Rate
    "CES0500000003",   # Avg Hourly Earnings — Private
    "CES0500000008",   # Avg Weekly Hours — Private
    "JTS000000000000000JOL", # JOLTS Job Openings
    "JTS000000000000000HIR", # JOLTS Hires
    "JTS000000000000000QUR", # JOLTS Quits
    # CPI breakdowns
    "CUUR0000SA0",     # CPI-U All Items
    "CUUR0000SA0L1E",  # CPI-U Core (less food & energy)
    "CUUR0000SAF1",    # CPI Food
    "CUUR0000SEHF01",  # CPI Shelter
    "CUUR0000SAM",     # CPI Medical Care
    "CUUR0000SETB01",  # CPI Gasoline
    "CUUR0000SAE1",    # CPI Education
    # PPI
    "WPUFD49104",      # PPI Final Demand
    "WPUFD4131",       # PPI Final Demand — Goods
    "WPUFD41312",      # PPI Final Demand — Services
    # Import / Export prices
    "EIUIR",           # Import Price Index — All
    "EIUIQ",           # Export Price Index — All
    # Productivity
    "PRS85006092",     # Nonfarm Business Labor Productivity
    "PRS85006112",     # Nonfarm Business Unit Labor Costs
]

SERIES_NAMES = {
    "CES0000000001": "Total Nonfarm Payrolls",
    "LNS14000000": "Unemployment Rate (U-3)",
    "LNS13327709": "U-6 Underemployment Rate",
    "CES0500000003": "Avg Hourly Earnings — Private",
    "CES0500000008": "Avg Weekly Hours — Private",
    "JTS000000000000000JOL": "JOLTS Job Openings",
    "JTS000000000000000HIR": "JOLTS Hires",
    "JTS000000000000000QUR": "JOLTS Quits",
    "CUUR0000SA0": "CPI-U All Items",
    "CUUR0000SA0L1E": "CPI-U Core (less food & energy)",
    "CUUR0000SAF1": "CPI Food",
    "CUUR0000SEHF01": "CPI Shelter",
    "CUUR0000SAM": "CPI Medical Care",
    "CUUR0000SETB01": "CPI Gasoline",
    "CUUR0000SAE1": "CPI Education",
    "WPUFD49104": "PPI Final Demand",
    "WPUFD4131": "PPI Final Demand — Goods",
    "WPUFD41312": "PPI Final Demand — Services",
    "EIUIR": "Import Price Index",
    "EIUIQ": "Export Price Index",
    "PRS85006092": "Nonfarm Business Labor Productivity",
    "PRS85006112": "Nonfarm Business Unit Labor Costs",
}

# BLS period codes to month numbers
_PERIOD_MAP = {f"M{m:02d}": m for m in range(1, 13)}


class BlsDataPlugin(DataPlugin):
    name = "data_bls"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        start_year = int(start[:4]) if start else 2015
        end_year = int(end[:4]) if end else 2024
        rows = []

        # BLS v1 allows max 10 years per request. Chunk requests so the
        # ingestor can probe and fetch the deepest available history.
        chunk_start = start_year
        while chunk_start <= end_year:
            chunk_end = min(chunk_start + 9, end_year)
            payload = {
                "seriesid": [symbol],
                "startyear": str(chunk_start),
                "endyear": str(chunk_end),
            }

            try:
                resp = requests.post(
                    BLS_API, json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.warning("BLS fetch failed for %s", symbol)
                return pd.DataFrame()

            if data.get("status") != "REQUEST_SUCCEEDED":
                logger.warning("BLS request not succeeded for %s: %s",
                               symbol, data.get("message", ""))
                return pd.DataFrame()

            series_data = data.get("Results", {}).get("series", [])
            if series_data and series_data[0].get("data"):
                for entry in series_data[0]["data"]:
                    year = entry.get("year")
                    period = entry.get("period", "")
                    value = entry.get("value")
                    month = _PERIOD_MAP.get(period)
                    if year and month and value:
                        try:
                            rows.append({
                                "date": pd.Timestamp(int(year), month, 1),
                                "value": float(value),
                            })
                        except (ValueError, TypeError):
                            continue
            chunk_start = chunk_end + 1

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").set_index("date")
        result = pd.DataFrame({
            "open": df["value"],
            "high": df["value"],
            "low": df["value"],
            "close": df["value"],
            "volume": 0,
        }, index=df.index)
        result.index.name = "date"
        return result

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {
            "name": SERIES_NAMES.get(symbol, symbol),
            "series_id": symbol,
            "source": "BLS",
            "type": "labor_statistic",
        }

    def list_symbols(self) -> list[str]:
        return list(DEFAULT_SERIES)

    def validate_key(self) -> bool:
        return True
