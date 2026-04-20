"""U.S. Treasury Fiscal Data plugin -- free, no API key needed."""
from __future__ import annotations

import logging

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

TREASURY_API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

ENDPOINTS = {
    # Debt & deficit
    "avg_interest_rates": "v2/accounting/od/avg_interest_rates",
    "debt_to_penny": "v2/accounting/od/debt_to_penny",
    "mspd_table1": "v1/debt/mspd/mspd_table_1",  # Monthly Statement of Public Debt
    "top_federal": "v2/revenue/rcm",               # Federal Revenue Collections
    # Daily Treasury rates
    "yield_curve": "v2/accounting/od/avg_interest_rates",  # yield curve via avg rates
    "treasury_rates": "v1/accounting/od/rates_of_exchange",
    # Savings & securities
    "tips_cpi": "v1/accounting/od/tips_cpi_data",          # TIPS CPI data
    "buybacks": "v2/accounting/od/securities_buyback_operations",
    # Fiscal data
    "federal_spending": "v2/payments/jfics/jfics_congress_district_summary",
}

# Which value column to extract per endpoint
_VALUE_COLUMN = {
    "avg_interest_rates": "avg_interest_rate_amt",
    "debt_to_penny": "tot_pub_debt_out_amt",
    "mspd_table1": "total_mil_amt",
    "top_federal": "net_collections_amt",
    "yield_curve": "avg_interest_rate_amt",
    "treasury_rates": "exchange_rate",
    "tips_cpi": "tips_cpi_index_value",
    "buybacks": "par_amt_accepted",
    "federal_spending": "total_obligation_amt",
}

ENDPOINT_NAMES = {
    "avg_interest_rates": "Average Interest Rates on U.S. Treasury Securities",
    "debt_to_penny": "U.S. Total Public Debt Outstanding",
    "mspd_table1": "Monthly Statement of Public Debt",
    "top_federal": "Federal Revenue Collections",
    "yield_curve": "Treasury Yield Curve (via avg rates)",
    "treasury_rates": "Treasury Rates of Exchange",
    "tips_cpi": "TIPS CPI Adjustment Index",
    "buybacks": "Treasury Buyback Operations",
    "federal_spending": "Federal Spending by District",
}


class TreasuryDataPlugin(DataPlugin):
    name = "data_treasury"

    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        import requests

        endpoint = ENDPOINTS.get(symbol)
        if not endpoint:
            logger.warning("Unknown Treasury symbol: %s", symbol)
            return pd.DataFrame()

        url = f"{TREASURY_API}/{endpoint}"
        params: dict[str, str | int] = {
            "sort": "-record_date",
            "page[size]": 1000,
        }
        if start:
            params["filter"] = f"record_date:gte:{start}"

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("Treasury fetch failed for %s", symbol)
            return pd.DataFrame()

        records = data.get("data", [])
        if not records:
            return pd.DataFrame()

        val_col = _VALUE_COLUMN.get(symbol, "")
        rows = []
        for rec in records:
            date_str = rec.get("record_date")
            raw_val = rec.get(val_col)
            if date_str and raw_val is not None:
                try:
                    rows.append({
                        "date": pd.Timestamp(date_str),
                        "value": float(raw_val),
                    })
                except (ValueError, TypeError):
                    continue

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).sort_values("date").set_index("date")

        # Filter by end date
        if end:
            df = df.loc[:end]

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
            "name": ENDPOINT_NAMES.get(symbol, symbol),
            "series_id": symbol,
            "source": "U.S. Treasury",
            "type": "fiscal_data",
        }

    def list_symbols(self) -> list[str]:
        return list(ENDPOINTS.keys())

    def validate_key(self) -> bool:
        return True
