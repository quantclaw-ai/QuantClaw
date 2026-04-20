"""European Central Bank data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

ECB_API = "https://data-api.ecb.europa.eu/service/data"

DEFAULT_SYMBOLS = [
    # FX rates (daily)
    "EXR/D.USD.EUR.SP00.A",       # EUR/USD
    "EXR/D.GBP.EUR.SP00.A",       # EUR/GBP
    "EXR/D.JPY.EUR.SP00.A",       # EUR/JPY
    "EXR/D.CHF.EUR.SP00.A",       # EUR/CHF
    "EXR/D.CNY.EUR.SP00.A",       # EUR/CNY
    "EXR/D.AUD.EUR.SP00.A",       # EUR/AUD
    "EXR/D.CAD.EUR.SP00.A",       # EUR/CAD
    # Policy rates
    "FM/B.U2.EUR.4F.KR.MRR_FR.LEV",  # Main refinancing rate
    "FM/B.U2.EUR.4F.KR.DFR.LEV",     # Deposit facility rate
    "FM/B.U2.EUR.4F.KR.MLFR.LEV",    # Marginal lending facility rate
    # Inflation
    "ICP/M.U2.N.000000.4.ANR",    # HICP — headline
    "ICP/M.U2.N.XEF000.4.ANR",    # HICP — core (ex energy & food)
    # Money supply
    "BSI/M.U2.N.V.M30.X.1.U2.2300.Z01.E",  # M3 money supply
    # Government bond yields (10y benchmark)
    "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y",  # EA 10y gov bond yield
    "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y",   # EA 2y gov bond yield
    # Bank lending
    "MIR/M.U2.B.A2A.A.R.A.2240.EUR.N",  # Lending rate — new business, NFC
    "MIR/M.U2.B.A2C.AM.R.A.2250.EUR.N", # Lending rate — mortgages
    # GDP
    "MNA/Q.Y.I9.W2.S1.S1.B.B1GQ._Z._Z._Z.EUR.LR.GY",  # EA GDP growth (q/q)
]

SYMBOL_NAMES = {
    "EXR/D.USD.EUR.SP00.A": "EUR/USD Exchange Rate",
    "EXR/D.GBP.EUR.SP00.A": "EUR/GBP Exchange Rate",
    "EXR/D.JPY.EUR.SP00.A": "EUR/JPY Exchange Rate",
    "EXR/D.CHF.EUR.SP00.A": "EUR/CHF Exchange Rate",
    "EXR/D.CNY.EUR.SP00.A": "EUR/CNY Exchange Rate",
    "EXR/D.AUD.EUR.SP00.A": "EUR/AUD Exchange Rate",
    "EXR/D.CAD.EUR.SP00.A": "EUR/CAD Exchange Rate",
    "FM/B.U2.EUR.4F.KR.MRR_FR.LEV": "ECB Main Refinancing Rate",
    "FM/B.U2.EUR.4F.KR.DFR.LEV": "ECB Deposit Facility Rate",
    "FM/B.U2.EUR.4F.KR.MLFR.LEV": "ECB Marginal Lending Rate",
    "ICP/M.U2.N.000000.4.ANR": "HICP Inflation — Headline",
    "ICP/M.U2.N.XEF000.4.ANR": "HICP Inflation — Core",
    "BSI/M.U2.N.V.M30.X.1.U2.2300.Z01.E": "Euro Area M3 Money Supply",
    "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y": "EA 10Y Gov Bond Yield",
    "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y": "EA 2Y Gov Bond Yield",
    "MIR/M.U2.B.A2A.A.R.A.2240.EUR.N": "EA Bank Lending Rate — NFC",
    "MIR/M.U2.B.A2C.AM.R.A.2250.EUR.N": "EA Mortgage Lending Rate",
    "MNA/Q.Y.I9.W2.S1.S1.B.B1GQ._Z._Z._Z.EUR.LR.GY": "EA GDP Growth (Q/Q)",
}


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """Split 'flowRef/key' on first slash."""
    idx = symbol.index("/")
    return (symbol[:idx], symbol[idx + 1:])


class EcbDataPlugin(DataPlugin):
    name = "data_ecb"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        try:
            flow_ref, key = _parse_symbol(symbol)
        except (ValueError, IndexError):
            logger.warning("ECB: invalid symbol format %s", symbol)
            return pd.DataFrame()

        url = f"{ECB_API}/{flow_ref}/{key}"
        params: dict[str, str] = {"format": "csvdata"}
        if start:
            params["startPeriod"] = start[:10]
        if end:
            params["endPeriod"] = end[:10]

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except Exception:
            logger.warning("ECB fetch failed for %s", symbol)
            return pd.DataFrame()

        try:
            from io import StringIO
            raw = pd.read_csv(StringIO(resp.text))

            if "TIME_PERIOD" not in raw.columns or "OBS_VALUE" not in raw.columns:
                logger.warning("ECB: unexpected columns for %s: %s",
                               symbol, list(raw.columns))
                return pd.DataFrame()

            raw["date"] = pd.to_datetime(raw["TIME_PERIOD"], errors="coerce")
            raw = raw.dropna(subset=["date"])
            raw = raw.set_index("date").sort_index()
            values = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")

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
            logger.warning("ECB parse failed for %s", symbol)
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        return {
            "name": SYMBOL_NAMES.get(symbol, symbol),
            "source": "ECB",
            "type": "monetary_indicator",
        }

    def list_symbols(self) -> list[str]:
        return list(DEFAULT_SYMBOLS)

    def validate_key(self) -> bool:
        return True
