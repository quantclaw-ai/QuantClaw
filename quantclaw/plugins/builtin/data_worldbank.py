"""World Bank Indicators data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

WB_API = "https://api.worldbank.org/v2/country"

_COUNTRIES = ["US", "CN", "GB", "JP", "DE", "IN", "BR", "KR", "AU", "CA", "MX", "ZA"]

_INDICATORS = {
    # GDP & growth
    "NY.GDP.MKTP.CD": "GDP (current USD)",
    "NY.GDP.MKTP.KD.ZG": "GDP Growth (annual %)",
    "NY.GDP.PCAP.CD": "GDP Per Capita (current USD)",
    # Inflation & prices
    "FP.CPI.TOTL.ZG": "CPI Inflation (annual %)",
    "NY.GDP.DEFL.KD.ZG": "GDP Deflator (annual %)",
    # Labor
    "SL.UEM.TOTL.ZS": "Unemployment (%)",
    "SL.TLF.ACTI.ZS": "Labor Force Participation (%)",
    # Trade & balance of payments
    "NE.EXP.GNFS.ZS": "Exports (% of GDP)",
    "NE.IMP.GNFS.ZS": "Imports (% of GDP)",
    "BN.CAB.XOKA.GD.ZS": "Current Account Balance (% of GDP)",
    "BX.KLT.DINV.WD.GD.ZS": "FDI Net Inflows (% of GDP)",
    # Debt & fiscal
    "GC.DOD.TOTL.GD.ZS": "Central Gov Debt (% of GDP)",
    "GC.BAL.CASH.GD.ZS": "Cash Surplus/Deficit (% of GDP)",
    # Demographics
    "SP.POP.TOTL": "Population Total",
    "SP.POP.GROW": "Population Growth (annual %)",
    # Financial
    "FR.INR.RINR": "Real Interest Rate (%)",
    "FM.LBL.BMNY.GD.ZS": "Broad Money (% of GDP)",
}

# Generate cross-product: top countries x all indicators
DEFAULT_SYMBOLS = [
    f"{country}/{ind}" for country in _COUNTRIES for ind in _INDICATORS
]


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """Split 'COUNTRY/INDICATOR' into (country, indicator)."""
    parts = symbol.split("/", 1)
    if len(parts) != 2:
        return ("US", symbol)
    return (parts[0], parts[1])


class WorldBankDataPlugin(DataPlugin):
    name = "data_worldbank"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        country, indicator = _parse_symbol(symbol)
        start_year = start[:4] if start else "2000"
        end_year = end[:4] if end else "2024"

        url = f"{WB_API}/{country}/indicator/{indicator}"
        params = {
            "date": f"{start_year}:{end_year}",
            "format": "json",
            "per_page": 1000,
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("World Bank fetch failed for %s", symbol)
            return pd.DataFrame()

        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            logger.warning("World Bank returned no data for %s", symbol)
            return pd.DataFrame()

        rows = []
        for entry in data[1]:
            value = entry.get("value")
            year = entry.get("date")
            if value is not None and year is not None:
                rows.append({"year": int(year), "value": float(value)})

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df = df.sort_values("year")
        df["date"] = pd.to_datetime(df["year"].astype(str) + "-01-01")
        df = df.set_index("date")

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
        country, indicator = _parse_symbol(symbol)
        return {
            "name": indicator,
            "country": country,
            "source": "World Bank",
            "type": "development_indicator",
        }

    def list_symbols(self) -> list[str]:
        return list(DEFAULT_SYMBOLS)

    def validate_key(self) -> bool:
        return True
