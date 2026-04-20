"""IMF Data data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

IMF_API = "https://www.imf.org/external/datamapper/api/v1"

_COUNTRIES = ["USA", "CHN", "GBR", "JPN", "DEU", "IND", "BRA", "KOR", "AUS", "CAN", "MEX"]

_INDICATORS = {
    "NGDP_RPCH": "Real GDP Growth (%)",
    "PCPIPCH": "CPI Inflation (%)",
    "LUR": "Unemployment Rate (%)",
    "BCA_NGDPD": "Current Account Balance (% of GDP)",
    "GGXWDG_NGDP": "Gov Gross Debt (% of GDP)",
    "GGXCNL_NGDP": "Gov Net Lending/Borrowing (% of GDP)",
    "NGDPD": "GDP (current USD billions)",
    "NGDPDPC": "GDP Per Capita (current USD)",
    "TM_RPCH": "Import Volume Growth (%)",
    "TX_RPCH": "Export Volume Growth (%)",
}

# Cross-product: countries x indicators
DEFAULT_SYMBOLS = [
    f"{ind}/{country}" for country in _COUNTRIES for ind in _INDICATORS
]


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """Split 'INDICATOR/COUNTRY' into (indicator, country)."""
    parts = symbol.split("/", 1)
    if len(parts) != 2:
        return (symbol, "USA")
    return (parts[0], parts[1])


class ImfDataPlugin(DataPlugin):
    name = "data_imf"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        indicator, country = _parse_symbol(symbol)
        url = f"{IMF_API}/{indicator}/{country}"

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("IMF fetch failed for %s", symbol)
            return pd.DataFrame()

        try:
            values = data.get("values", {}).get(indicator, {}).get(country, {})
            if not values:
                logger.warning("IMF returned no data for %s", symbol)
                return pd.DataFrame()

            start_year = int(start[:4]) if start else 0
            end_year = int(end[:4]) if end else 9999

            rows = []
            for year_str, val in values.items():
                year = int(year_str)
                if start_year <= year <= end_year:
                    rows.append({"year": year, "value": float(val)})

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows).sort_values("year")
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
        except Exception:
            logger.warning("IMF parse failed for %s", symbol)
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        indicator, country = _parse_symbol(symbol)
        return {
            "name": indicator,
            "country": country,
            "source": "IMF",
            "type": "economic_indicator",
        }

    def list_symbols(self) -> list[str]:
        return list(DEFAULT_SYMBOLS)

    def validate_key(self) -> bool:
        return True
