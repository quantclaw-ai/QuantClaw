"""Interactive Brokers plugin -- default broker."""
from __future__ import annotations
from quantclaw.plugins.interfaces import (
    BrokerPlugin,
    Position,
    Order,
    OrderResult,
    Account,
)


class IBBrokerPlugin(BrokerPlugin):
    name = "broker_ib"

    def __init__(self):
        self._connected = False
        self._paper = True

    def connect(self, credentials: dict) -> None:
        self._paper = credentials.get("paper", True)
        self._connected = True

    def get_positions(self) -> list[Position]:
        return []

    def submit_order(self, order: Order) -> OrderResult:
        return OrderResult(
            order_id="", status="rejected", filled_qty=0, filled_price=0
        )

    def get_account(self) -> Account:
        return Account(
            equity=100000, cash=100000, buying_power=100000, positions=[]
        )

    def is_market_open(self) -> bool:
        from datetime import datetime

        try:
            import pytz

            now = datetime.now(pytz.timezone("US/Eastern"))
        except ImportError:
            now = datetime.now()
        if now.weekday() >= 5:
            return False
        return 930 <= now.hour * 100 + now.minute <= 1600
