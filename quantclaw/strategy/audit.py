"""Backtest audit trail: event-by-event detail of every trade decision."""
from __future__ import annotations
import json
import csv
from io import StringIO
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AuditEntry:
    date: str
    event_type: str  # "signal", "allocation", "risk_check", "trade", "rebalance", "skip"
    details: dict


@dataclass
class BacktestAudit:
    strategy_name: str
    start_date: str
    end_date: str
    entries: list[AuditEntry] = field(default_factory=list)

    def add_signal(self, date: str, scores: dict):
        self.entries.append(AuditEntry(
            date=date, event_type="signal",
            details={"scores": {k: round(v, 4) for k, v in scores.items()}},
        ))

    def add_allocation(self, date: str, weights: dict):
        self.entries.append(AuditEntry(
            date=date, event_type="allocation",
            details={"weights": {k: round(v, 4) for k, v in weights.items()}},
        ))

    def add_risk_check(self, date: str, passed: bool, drawdown: float):
        self.entries.append(AuditEntry(
            date=date, event_type="risk_check",
            details={"passed": passed, "drawdown": round(drawdown, 4)},
        ))

    def add_trade(self, date: str, symbol: str, qty: float, price: float,
                  side: str, cost: float, slippage: float = 0):
        self.entries.append(AuditEntry(
            date=date, event_type="trade",
            details={
                "symbol": symbol, "qty": round(qty, 2), "price": round(price, 2),
                "side": side, "cost": round(cost, 4), "slippage": round(slippage, 4),
            },
        ))

    def add_rebalance(self, date: str, old_positions: dict, new_positions: dict):
        changes = {}
        all_symbols = set(list(old_positions.keys()) + list(new_positions.keys()))
        for sym in all_symbols:
            old_w = old_positions.get(sym, 0)
            new_w = new_positions.get(sym, 0)
            if abs(old_w - new_w) > 0.001:
                changes[sym] = {"old": round(old_w, 4), "new": round(new_w, 4)}
        if changes:
            self.entries.append(AuditEntry(
                date=date, event_type="rebalance",
                details={"changes": changes},
            ))

    def add_skip(self, date: str, reason: str):
        self.entries.append(AuditEntry(
            date=date, event_type="skip",
            details={"reason": reason},
        ))

    def summary(self) -> dict:
        """Get audit summary statistics."""
        trade_count = sum(1 for e in self.entries if e.event_type == "trade")
        signal_count = sum(1 for e in self.entries if e.event_type == "signal")
        skip_count = sum(1 for e in self.entries if e.event_type == "skip")
        risk_checks = [e for e in self.entries if e.event_type == "risk_check"]
        risk_blocks = sum(1 for e in risk_checks if not e.details.get("passed", True))
        total_cost = sum(e.details.get("cost", 0) for e in self.entries if e.event_type == "trade")
        return {
            "strategy": self.strategy_name,
            "period": f"{self.start_date} to {self.end_date}",
            "total_entries": len(self.entries),
            "signals_generated": signal_count,
            "trades_executed": trade_count,
            "rebalances_skipped": skip_count,
            "risk_blocks": risk_blocks,
            "total_transaction_cost": round(total_cost, 2),
        }

    def to_json(self) -> str:
        return json.dumps({
            "strategy": self.strategy_name,
            "start": self.start_date,
            "end": self.end_date,
            "summary": self.summary(),
            "entries": [{"date": e.date, "type": e.event_type, "details": e.details} for e in self.entries],
        }, indent=2)

    def to_csv(self) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "event_type", "details"])
        for e in self.entries:
            writer.writerow([e.date, e.event_type, json.dumps(e.details)])
        return output.getvalue()

    def filter_by_type(self, event_type: str) -> list[AuditEntry]:
        return [e for e in self.entries if e.event_type == event_type]

    def filter_by_date(self, date: str) -> list[AuditEntry]:
        return [e for e in self.entries if e.date == date]

    def filter_by_symbol(self, symbol: str) -> list[AuditEntry]:
        return [e for e in self.entries if symbol in str(e.details)]
