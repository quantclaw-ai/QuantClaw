"""Bank for International Settlements data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

BIS_API = "https://stats.bis.org/api/v2/data/dataflow/BIS"

DEFAULT_SYMBOLS = [
    # Effective exchange rates (broad, nominal)
    "WS_EER/M.N.B.US",    # US
    "WS_EER/M.N.B.XM",    # Euro area
    "WS_EER/M.N.B.CN",    # China
    "WS_EER/M.N.B.JP",    # Japan
    "WS_EER/M.N.B.GB",    # UK
    # Total credit to private non-financial sector (% of GDP)
    "WS_CREDIT/Q.US.P.A.M.770.A",   # US
    "WS_CREDIT/Q.CN.P.A.M.770.A",   # China
    "WS_CREDIT/Q.XM.P.A.M.770.A",   # Euro area
    "WS_CREDIT/Q.JP.P.A.M.770.A",   # Japan
    "WS_CREDIT/Q.GB.P.A.M.770.A",   # UK
    # Credit-to-GDP gap (early warning for banking crises)
    "WS_CREDIT/Q.US.P.A.G.770.A",   # US credit gap
    "WS_CREDIT/Q.CN.P.A.G.770.A",   # China credit gap
    # Cross-border banking claims
    "WS_CBS_PUB/Q.S.5A.4P.TC1.A.TO1.A.A.US",  # Claims on US
    "WS_CBS_PUB/Q.S.5A.4P.TC1.A.TO1.A.A.CN",  # Claims on China
    # Residential property prices (real, y/y)
    "WS_SPP/Q.US.R.628",   # US property prices
    "WS_SPP/Q.GB.R.628",   # UK property prices
    "WS_SPP/Q.CN.R.628",   # China property prices
    "WS_SPP/Q.DE.R.628",   # Germany property prices
    "WS_SPP/Q.JP.R.628",   # Japan property prices
    # Global liquidity — USD credit to non-banks outside US
    "WS_GLI/Q.1C.B.USD.TO1.A",
]

SYMBOL_NAMES = {
    "WS_EER/M.N.B.US": "US Effective Exchange Rate",
    "WS_EER/M.N.B.XM": "Euro Area Effective Exchange Rate",
    "WS_EER/M.N.B.CN": "China Effective Exchange Rate",
    "WS_EER/M.N.B.JP": "Japan Effective Exchange Rate",
    "WS_EER/M.N.B.GB": "UK Effective Exchange Rate",
    "WS_CREDIT/Q.US.P.A.M.770.A": "US Total Credit to Private NFS",
    "WS_CREDIT/Q.CN.P.A.M.770.A": "China Total Credit to Private NFS",
    "WS_CREDIT/Q.XM.P.A.M.770.A": "Euro Area Total Credit to Private NFS",
    "WS_CREDIT/Q.JP.P.A.M.770.A": "Japan Total Credit to Private NFS",
    "WS_CREDIT/Q.GB.P.A.M.770.A": "UK Total Credit to Private NFS",
    "WS_CREDIT/Q.US.P.A.G.770.A": "US Credit-to-GDP Gap",
    "WS_CREDIT/Q.CN.P.A.G.770.A": "China Credit-to-GDP Gap",
    "WS_CBS_PUB/Q.S.5A.4P.TC1.A.TO1.A.A.US": "Cross-Border Claims on US",
    "WS_CBS_PUB/Q.S.5A.4P.TC1.A.TO1.A.A.CN": "Cross-Border Claims on China",
    "WS_SPP/Q.US.R.628": "US Residential Property Prices (Real)",
    "WS_SPP/Q.GB.R.628": "UK Residential Property Prices (Real)",
    "WS_SPP/Q.CN.R.628": "China Residential Property Prices (Real)",
    "WS_SPP/Q.DE.R.628": "Germany Residential Property Prices (Real)",
    "WS_SPP/Q.JP.R.628": "Japan Residential Property Prices (Real)",
    "WS_GLI/Q.1C.B.USD.TO1.A": "Global USD Credit to Non-Banks Outside US",
}


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """Split 'DATASET/KEY' on first slash."""
    idx = symbol.index("/")
    return (symbol[:idx], symbol[idx + 1:])


class BisDataPlugin(DataPlugin):
    name = "data_bis"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        try:
            dataset, key = _parse_symbol(symbol)
        except (ValueError, IndexError):
            logger.warning("BIS: invalid symbol format %s", symbol)
            return pd.DataFrame()

        url = f"{BIS_API}/{dataset}/1.0/{key}"
        params: dict[str, str] = {
            "detail": "dataonly",
            "format": "csv",
        }
        if start:
            params["startPeriod"] = start[:10]
        if end:
            params["endPeriod"] = end[:10]

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except Exception:
            logger.warning("BIS fetch failed for %s", symbol)
            return pd.DataFrame()

        try:
            from io import StringIO
            raw = pd.read_csv(StringIO(resp.text))

            # BIS CSV uses TIME_PERIOD and OBS_VALUE columns
            time_col = None
            val_col = None
            for col in raw.columns:
                cl = col.upper()
                if "TIME" in cl or "PERIOD" in cl:
                    time_col = col
                if "OBS" in cl and "VALUE" in cl:
                    val_col = col

            if time_col is None or val_col is None:
                logger.warning("BIS: could not find time/value columns for %s: %s",
                               symbol, list(raw.columns))
                return pd.DataFrame()

            raw["date"] = pd.to_datetime(raw[time_col], errors="coerce")
            raw = raw.dropna(subset=["date"])
            raw = raw.set_index("date").sort_index()
            values = pd.to_numeric(raw[val_col], errors="coerce")

            result = pd.DataFrame({
                "open": values,
                "high": values,
                "low": values,
                "close": values,
                "volume": 0,
            }, index=raw.index)
            result.index.name = "date"
            return result.dropna(subset=["close"])
        except Exception:
            logger.warning("BIS parse failed for %s", symbol)
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {
            "name": SYMBOL_NAMES.get(symbol, symbol),
            "source": "BIS",
            "type": "international_financial_statistic",
        }

    def list_symbols(self) -> list[str]:
        return list(DEFAULT_SYMBOLS)

    def validate_key(self) -> bool:
        return True
