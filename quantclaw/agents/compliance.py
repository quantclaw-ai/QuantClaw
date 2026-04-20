"""Compliance: checks trades and portfolio against risk rules."""
from __future__ import annotations

import logging
from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ComplianceAgent(BaseAgent):
    name = "compliance"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        task_type = task.get("task", "check_rules")
        violations: list[dict] = []

        risk = self._config.get("risk", {})
        max_drawdown = risk.get("max_drawdown", -0.10)
        max_position_pct = risk.get("max_position_pct", 0.05)

        # Check proposed trades
        trades = task.get("trades", [])
        portfolio_value = task.get("portfolio_value", 100000)
        current_drawdown = task.get("current_drawdown", 0.0)

        # Rule 1: Position size limit
        for trade in trades:
            symbol = trade.get("symbol", "unknown")
            value = abs(trade.get("value", 0))
            position_pct = value / portfolio_value if portfolio_value > 0 else 0
            if position_pct > max_position_pct:
                violations.append({
                    "rule": "position_size",
                    "symbol": symbol,
                    "detail": f"Position {position_pct:.1%} exceeds limit {max_position_pct:.1%}",
                    "severity": "high",
                })

        # Rule 2: Drawdown limit
        if current_drawdown < max_drawdown:
            violations.append({
                "rule": "drawdown_limit",
                "detail": f"Current drawdown {current_drawdown:.1%} exceeds limit {max_drawdown:.1%}",
                "severity": "critical",
            })

        # Rule 3: Restricted symbols
        restricted = set(self._config.get("restricted_symbols", []))
        for trade in trades:
            symbol = trade.get("symbol", "")
            if symbol in restricted:
                violations.append({
                    "rule": "restricted_symbol",
                    "symbol": symbol,
                    "detail": f"{symbol} is on the restricted list",
                    "severity": "critical",
                })

        if violations:
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={
                    "compliant": False,
                    "violations": violations,
                    "checked_trades": len(trades),
                },
            )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "compliant": True,
                "violations": [],
                "checked_trades": len(trades),
            },
        )
