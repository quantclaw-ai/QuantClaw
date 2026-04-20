"""Progressive trust system with risk guardrails."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantclaw.events.bus import EventBus
    from quantclaw.orchestration.playbook import Playbook


class TrustLevel(IntEnum):
    OBSERVER = 0       # Research, analyze, report
    PAPER_TRADER = 1   # Paper trade within limits
    PROVEN = 2         # Can request live trading
    TRUSTED = 3        # Live trading within budget
    AUTONOMOUS = 4     # Full autonomy within budget


# Actions that require escalation to Plan Mode regardless of trust level
SAFETY_CRITICAL_ACTIONS = frozenset({
    "live_trade",
    "increase_position_size",
    "new_asset_class",
    "first_paper_trade",
})


@dataclass
class RiskGuardrails:
    max_drawdown: float = -0.10
    max_position_pct: float = 0.05
    auto_liquidate_at: float = -0.15

    @classmethod
    def from_config(cls, config: dict) -> RiskGuardrails:
        risk = config.get("risk", {})
        return cls(
            max_drawdown=risk.get("max_drawdown", -0.10),
            max_position_pct=risk.get("max_position_pct", 0.05),
            auto_liquidate_at=risk.get("auto_liquidate_at", -0.15),
        )

    def check_position_size(self, position_pct: float, portfolio_value: float) -> bool:
        return position_pct <= self.max_position_pct

    def check_drawdown(self, current_drawdown: float) -> bool:
        return current_drawdown > self.max_drawdown


class TrustManager:
    """Manages progressive trust levels and performance tracking.

    Accepts an optional EventBus to emit trust.level_changed events,
    and an optional Playbook to persist trust milestones across restarts.
    """

    def __init__(
        self,
        initial_level: TrustLevel = TrustLevel.OBSERVER,
        bus: EventBus | None = None,
        playbook: Playbook | None = None,
    ):
        self._level = initial_level
        self._trade_results: list[float] = []
        self._bus = bus
        self._playbook = playbook

    @property
    def level(self) -> TrustLevel:
        return self._level

    async def upgrade(self, target: TrustLevel) -> None:
        if target > self._level + 1:
            raise ValueError(
                f"Cannot skip levels: current={self._level.name}, target={target.name}"
            )
        old_level = self._level
        self._level = target

        # Emit trust level changed event
        if self._bus:
            from quantclaw.events.types import Event, EventType
            await self._bus.publish(Event(
                type=EventType.TRUST_LEVEL_CHANGED,
                payload={
                    "old_level": old_level.name,
                    "new_level": target.name,
                    "old_level_id": int(old_level),
                    "new_level_id": int(target),
                },
                source_agent="scheduler",
            ))

        # Persist to playbook
        if self._playbook:
            from quantclaw.orchestration.playbook import EntryType
            await self._playbook.add(EntryType.TRUST_MILESTONE, {
                "old_level": old_level.name,
                "new_level": target.name,
                "metrics": self.get_metrics(),
            }, tags=["trust", target.name])

    @classmethod
    async def from_playbook(cls, playbook: Playbook, bus: EventBus | None = None) -> TrustManager:
        """Restore trust level from playbook on startup."""
        from quantclaw.orchestration.playbook import EntryType
        milestones = await playbook.query(entry_type=EntryType.TRUST_MILESTONE)
        level = TrustLevel.OBSERVER
        if milestones:
            last = milestones[-1]
            try:
                level = TrustLevel[last.content["new_level"]]
            except (KeyError, ValueError):
                pass
        return cls(initial_level=level, bus=bus, playbook=playbook)

    def can_research(self) -> bool:
        return self._level >= TrustLevel.OBSERVER

    def can_paper_trade(self) -> bool:
        return self._level >= TrustLevel.PAPER_TRADER

    def can_live_trade(self) -> bool:
        return self._level >= TrustLevel.TRUSTED

    def requires_escalation(self, action: str) -> bool:
        if action in SAFETY_CRITICAL_ACTIONS:
            return True
        if action == "paper_trade" and self._level < TrustLevel.PAPER_TRADER:
            return True
        return False

    def record_trade_result(self, profit: float) -> None:
        self._trade_results.append(profit)

    async def check_auto_upgrade(self) -> bool:
        """Check if performance merits a trust upgrade. Returns True if upgraded."""
        metrics = self.get_metrics()
        total = metrics["total_trades"]
        win_rate = metrics["win_rate"]
        pnl = metrics["total_pnl"]

        # Level 0 -> 1: Completed 5+ paper trades
        if self._level == TrustLevel.OBSERVER and total >= 5:
            await self.upgrade(TrustLevel.PAPER_TRADER)
            return True

        # Level 1 -> 2: 20+ trades with positive P&L
        if self._level == TrustLevel.PAPER_TRADER and total >= 20 and pnl > 0:
            await self.upgrade(TrustLevel.PROVEN)
            return True

        # Level 2 -> 3: 50+ trades with >45% win rate and positive P&L
        if self._level == TrustLevel.PROVEN and total >= 50 and win_rate > 0.45 and pnl > 0:
            await self.upgrade(TrustLevel.TRUSTED)
            return True

        # Level 3 -> 4: 100+ trades with >50% win rate
        if self._level == TrustLevel.TRUSTED and total >= 100 and win_rate > 0.50 and pnl > 0:
            await self.upgrade(TrustLevel.AUTONOMOUS)
            return True

        return False

    def get_metrics(self) -> dict:
        if not self._trade_results:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
        wins = sum(1 for p in self._trade_results if p > 0)
        return {
            "total_trades": len(self._trade_results),
            "win_rate": wins / len(self._trade_results),
            "total_pnl": sum(self._trade_results),
        }
