"""US Equities asset plugin -- default asset class."""
from __future__ import annotations
from quantclaw.plugins.interfaces import AssetPlugin, TradingHours

SP500_TOP_100 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "JNJ",
    "V", "UNH", "HD", "PG", "MA", "DIS", "BAC", "XOM", "CSCO", "PFE",
    "INTC", "VZ", "KO", "PEP", "MRK", "ABT", "NKE", "CVX", "CRM", "AMD",
    "QCOM", "TXN", "COST", "LOW", "CAT", "UPS", "GS", "MS", "BLK", "SCHW",
    "AXP", "C", "USB", "PNC", "CME", "ICE", "LLY", "ABBV", "TMO",
    "DHR", "BMY", "AMGN", "GILD", "VRTX", "ISRG", "MDT", "CI", "WFC",
    "HON", "RTX", "BA", "LMT", "DE", "MMM", "GD", "ITW", "EMR", "WM",
    "AVGO", "ADBE", "NOW", "INTU", "AMAT", "MU", "ORCL", "PANW", "SNPS", "CDNS",
    "MRVL", "FTNT", "PLTR", "CRWD", "MCD", "NKE", "LOW", "SBUX", "TJX",
    "BKNG", "ABNB", "ORLY", "ROST", "DHI", "LEN", "GE", "UNP", "SPY", "QQQ",
]


class USEquitiesAssetPlugin(AssetPlugin):
    name = "asset_us_equities"

    def get_default_universe(self) -> list[str]:
        return SP500_TOP_100

    def get_trading_hours(self) -> TradingHours:
        return TradingHours(
            market_open="09:30",
            market_close="16:00",
            timezone="US/Eastern",
            trading_days=[0, 1, 2, 3, 4],
        )

    def get_symbol_info(self, symbol: str) -> dict:
        return {"symbol": symbol, "asset_class": "equity", "exchange": "US"}
