"""OpenInsider (SEC Form 4) data plugin -- free, no API key needed."""
from __future__ import annotations

import logging
import re

import pandas as pd

from quantclaw.plugins.interfaces import DataPlugin

logger = logging.getLogger(__name__)

SCREENER_URL = (
    "http://openinsider.com/screener"
    "?s={symbol}&o=&pl=&ph=&ll=&lh="
    "&fd=730&fdr=&td=0&tdr="
    "&feession=true&cession=true"
    "&ac=true&ic=true&fc=true&f2c=true"
    "&net=true&oc=true"
)


def _parse_trades(html: str) -> pd.DataFrame:
    """Extract the insider-trade table from OpenInsider HTML using bs4."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("bs4 not installed, OpenInsider parsing unavailable")
        return pd.DataFrame()

    try:
        soup = BeautifulSoup(html, "html.parser")
        # Find the table that has insider trade columns
        # The real table has headers: X, Filing Date, Trade Date, Ticker, ...
        # with non-breaking spaces (\xa0) in header text
        best_table = None
        best_rows = 0
        for table in soup.find_all("table"):
            all_rows = table.find_all("tr")
            if len(all_rows) < 5:
                continue
            header_row = all_rows[0]
            headers = [
                th.get_text(strip=True).replace("\xa0", " ")
                for th in header_row.find_all(["th", "td"])
            ]
            # The trades table has 10+ columns including "Ticker" and "Price"
            header_lower = [h.lower() for h in headers]
            if "ticker" in header_lower and "price" in header_lower:
                if len(all_rows) > best_rows:
                    best_table = table
                    best_rows = len(all_rows)

        if best_table is None:
            return pd.DataFrame()

        all_rows = best_table.find_all("tr")
        headers = [
            th.get_text(strip=True).replace("\xa0", " ")
            for th in all_rows[0].find_all(["th", "td"])
        ]

        data = []
        for row in all_rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) == len(headers):
                data.append(cells)

        if data:
            return pd.DataFrame(data, columns=headers)

    except Exception:
        logger.warning("Failed to parse OpenInsider HTML")

    return pd.DataFrame()


class OpenInsiderDataPlugin(DataPlugin):
    name = "data_openinsider"

    def _fetch_raw(self, symbol: str) -> pd.DataFrame:
        import requests

        url = SCREENER_URL.format(symbol=symbol.upper())
        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (compatible; QuantClaw/1.0)",
            })
            resp.raise_for_status()
        except Exception:
            logger.warning("OpenInsider request failed for %s", symbol)
            return pd.DataFrame()

        return _parse_trades(resp.text)

    # ------------------------------------------------------------------
    def fetch_ohlcv(
        self, symbol: str, start: str, end: str, freq: str = "1d",
    ) -> pd.DataFrame:
        return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        df = self._fetch_raw(symbol)
        if df.empty:
            return {
                "recent_buys": 0,
                "recent_sells": 0,
                "net_insider_activity": 0,
                "last_trade_date": None,
            }

        # Normalise column names for lookup
        cols_lower = {c.lower().strip(): c for c in df.columns}

        # Identify trade-type column
        tt_col = None
        for candidate in ("trade type", "tradetype", "type"):
            if candidate in cols_lower:
                tt_col = cols_lower[candidate]
                break

        buys, sells = 0, 0
        if tt_col is not None:
            types = df[tt_col].astype(str).str.lower()
            buys = int(types.str.contains("purchase|buy", na=False).sum())
            sells = int(types.str.contains("sale|sell", na=False).sum())

        # Identify date column
        date_col = None
        for candidate in ("filing date", "trade date", "date"):
            if candidate in cols_lower:
                date_col = cols_lower[candidate]
                break

        last_date = None
        if date_col is not None:
            try:
                dates = pd.to_datetime(df[date_col], errors="coerce")
                last_date = str(dates.dropna().max().date())
            except Exception:
                pass

        return {
            "recent_buys": buys,
            "recent_sells": sells,
            "net_insider_activity": buys - sells,
            "last_trade_date": last_date,
        }

    def available_fields(self) -> dict[str, list[str]]:
        return {
            "insider": [
                "trade_date", "insider_name", "title",
                "trade_type", "price", "qty", "owned", "value",
            ],
        }

    def fetch_fields(
        self, symbol: str, fields: list[str],
        start: str = "", end: str = "",
    ) -> pd.DataFrame:
        df = self._fetch_raw(symbol)
        if df.empty:
            return pd.DataFrame()

        # Normalise column names: lowercase, strip whitespace
        df.columns = [c.lower().strip() for c in df.columns]

        # Map requested field names to available columns
        alias_map: dict[str, list[str]] = {
            "trade_date": ["trade date", "filing date", "date"],
            "insider_name": ["insider name", "insidername", "insider"],
            "title": ["title"],
            "trade_type": ["trade type", "tradetype", "type"],
            "price": ["price"],
            "qty": ["qty", "quantity", "shares"],
            "owned": ["owned", "shares owned"],
            "value": ["value"],
        }

        rename: dict[str, str] = {}
        for field_name in fields:
            candidates = alias_map.get(field_name, [field_name])
            for c in candidates:
                if c in df.columns:
                    rename[c] = field_name
                    break

        if not rename:
            return pd.DataFrame()

        result = df[list(rename.keys())].rename(columns=rename)

        # Try to set a date index
        date_field = None
        for d in ("trade_date", "filing date", "trade date", "date"):
            if d in result.columns:
                date_field = d
                break
            if d in df.columns:
                result[d] = df[d]
                date_field = d
                break

        if date_field:
            try:
                result[date_field] = pd.to_datetime(
                    result[date_field], errors="coerce",
                )
                result = result.dropna(subset=[date_field])
                result = result.set_index(date_field).sort_index()
                result.index.name = "date"
            except Exception:
                pass

        if start:
            result = result.loc[start:]
        if end:
            result = result.loc[:end]

        # Keep only requested fields in output columns
        keep = [f for f in fields if f in result.columns]
        return result[keep] if keep else result

    def list_symbols(self) -> list[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "DIS",
            "BAC", "XOM", "CSCO", "PFE", "INTC",
        ]

    def validate_key(self) -> bool:
        return True
