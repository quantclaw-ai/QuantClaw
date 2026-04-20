"""Sentinel: event-driven monitoring and alerting.

Code-only daemon agent. Watches EventBus for alert patterns,
fires notifications via chat.narrative and the notification system.
No LLM calls — pure pattern matching on events.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus
from quantclaw.events.types import Event, EventType

logger = logging.getLogger(__name__)

# Default alert rules
DEFAULT_RULES = {
    "agent_failure_streak": {
        "description": "Alert when an agent fails 3+ times in a row",
        "threshold": 3,
        "severity": "high",
    },
    "drawdown_warning": {
        "description": "Alert when drawdown approaches limit",
        "threshold_pct": 0.80,  # Alert at 80% of max drawdown
        "severity": "critical",
    },
    "trade_failure": {
        "description": "Alert on any trade execution failure",
        "severity": "critical",
    },
    "cost_warning": {
        "description": "Alert when cost budget warning fires",
        "severity": "high",
    },
}


class SentinelAgent(BaseAgent):
    name = "sentinel"
    model = "sonnet"
    daemon = True

    def __init__(self, bus, config):
        super().__init__(bus, config)
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._alerts_fired: list[dict] = []
        self._rules = {**DEFAULT_RULES, **config.get("sentinel_rules", {})}

    async def execute(self, task: dict) -> AgentResult:
        """Return current alert status."""
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "active_rules": len(self._rules),
                "alerts_fired": len(self._alerts_fired),
                "recent_alerts": self._alerts_fired[-10:],
                "failure_counts": dict(self._failure_counts),
            },
        )

    async def on_event(self, event: Event) -> None:
        """Process incoming events against alert rules."""
        event_type = str(event.type)

        # Rule: Agent failure streak
        if event_type == "agent.task_failed":
            agent = event.payload.get("agent", "")
            self._failure_counts[agent] += 1
            threshold = self._rules.get("agent_failure_streak", {}).get("threshold", 3)
            if self._failure_counts[agent] >= threshold:
                await self._fire_alert(
                    rule="agent_failure_streak",
                    message=f"Agent '{agent}' has failed {self._failure_counts[agent]} times in a row",
                    severity=self._rules["agent_failure_streak"]["severity"],
                    data={"agent": agent, "count": self._failure_counts[agent]},
                )

        # Reset failure count on success
        if event_type == "agent.task_completed":
            agent = event.payload.get("agent", "")
            self._failure_counts[agent] = 0

        # Rule: Trade execution failure
        if event_type == "trade.reconciliation_fail":
            await self._fire_alert(
                rule="trade_failure",
                message=f"Trade reconciliation failed: {event.payload}",
                severity="critical",
                data=event.payload,
            )

        # Rule: Cost budget warning
        if event_type == "cost.budget_warning":
            spent = event.payload.get("spent", 0)
            budget = event.payload.get("budget", 0)
            await self._fire_alert(
                rule="cost_warning",
                message=f"Cost budget warning: ${spent:.2f} spent of ${budget:.2f} budget",
                severity="high",
                data=event.payload,
            )

        # Rule: Market gap detected
        if event_type == "market.gap_detected":
            symbol = event.payload.get("symbol", "unknown")
            gap_pct = event.payload.get("gap_pct", 0)
            await self._fire_alert(
                rule="market_gap",
                message=f"Market gap detected: {symbol} {gap_pct:+.1%}",
                severity="high",
                data=event.payload,
            )

        # Rule: Market regime change
        if event_type == "market.regime_change":
            await self._fire_alert(
                rule="regime_change",
                message=f"Market regime change detected: {event.payload.get('new_regime', 'unknown')}",
                severity="high",
                data=event.payload,
            )

    async def _fire_alert(self, rule: str, message: str, severity: str, data: dict) -> None:
        """Fire an alert — emit chat.narrative + log."""
        alert = {
            "rule": rule,
            "message": message,
            "severity": severity,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._alerts_fired.append(alert)

        # Keep only last 100 alerts
        if len(self._alerts_fired) > 100:
            self._alerts_fired = self._alerts_fired[-100:]

        logger.warning("Sentinel alert [%s]: %s", severity, message)

        # Emit to chat so CEO sees it
        severity_emoji = {"critical": "!!", "high": "!", "medium": "", "low": ""}
        prefix = severity_emoji.get(severity, "")

        await self._bus.publish(Event(
            type=EventType.CHAT_NARRATIVE,
            payload={
                "message": f"[ALERT{' ' + prefix if prefix else ''}] {message}",
                "role": "sentinel",
            },
            source_agent="sentinel",
        ))
