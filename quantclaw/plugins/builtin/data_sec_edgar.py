"""SEC EDGAR data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "QuantClaw contact@quantclaw.com"}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

KEY_CONCEPTS = [
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss", "Assets", "Liabilities",
    "StockholdersEquity", "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
]


class SecEdgarDataPlugin(DataPlugin):
    name = "data_sec_edgar"
    _cik_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    def _resolve_cik(self, symbol: str) -> str | None:
        import requests

        upper = symbol.upper()
        if upper in self._cik_cache:
            return self._cik_cache[upper]

        try:
            resp = requests.get(TICKERS_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("Failed to fetch SEC tickers JSON")
            return None

        for entry in data.values():
            tick = str(entry.get("ticker", "")).upper()
            cik = str(entry.get("cik_str", ""))
            self._cik_cache[tick] = cik.zfill(10)

        return self._cik_cache.get(upper)

    def _fetch_facts(self, symbol: str) -> dict | None:
        import requests

        cik = self._resolve_cik(symbol)
        if not cik:
            return None
        try:
            resp = requests.get(
                FACTS_URL.format(cik=cik), headers=HEADERS, timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("Failed to fetch EDGAR facts for %s", symbol)
            return None

    @staticmethod
    def _extract_concept(facts: dict, concept: str) -> list[dict]:
        """Pull filing records for a us-gaap concept."""
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        node = us_gaap.get(concept, {})
        units = node.get("units", {})
        # Prefer USD, fall back to first available unit
        for unit_key in ("USD", "USD/shares"):
            if unit_key in units:
                return units[unit_key]
        if units:
            return next(iter(units.values()))
        return []

    # ------------------------------------------------------------------
    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        facts = self._fetch_facts(symbol)
        if not facts:
            return {}
        result: dict = {}
        for concept in KEY_CONCEPTS:
            records = self._extract_concept(facts, concept)
            if records:
                latest = records[-1]
                result[concept] = {
                    "value": latest.get("val"),
                    "filed": latest.get("filed"),
                    "form": latest.get("form"),
                }
        return result

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "fundamentals": [
                "Revenues", "NetIncomeLoss", "Assets", "Liabilities",
                "StockholdersEquity", "EarningsPerShareBasic",
            ],
        }

    def fetch_fields(
        self, symbol: str, fields: list[str],
        start: str = "", end: str = "",
    ) -> pd.DataFrame:
        facts = self._fetch_facts(symbol)
        if not facts:
            return pd.DataFrame()

        series: dict[str, pd.Series] = {}
        for concept in fields:
            records = self._extract_concept(facts, concept)
            if not records:
                continue
            dates, vals = [], []
            for r in records:
                filed = r.get("filed")
                val = r.get("val")
                if filed is not None and val is not None:
                    dates.append(pd.Timestamp(filed))
                    vals.append(float(val))
            if dates:
                s = pd.Series(vals, index=pd.DatetimeIndex(dates, name="date"))
                s = s[~s.index.duplicated(keep="last")]
                series[concept] = s

        if not series:
            return pd.DataFrame()

        df = pd.DataFrame(series)
        df.index.name = "date"
        df = df.sort_index()

        if start:
            df = df.loc[start:]
        if end:
            df = df.loc[:end]

        return df

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS",
            "BAC", "XOM", "CSCO", "PFE", "INTC",
        ]

    def validate_key(self) -> bool:
        return True
