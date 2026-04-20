"""Risk Monitor: portfolio-level risk analysis.

Code-only agent — no LLM calls. Checks drawdown, concentration,
diversification, and exposure against configured limits.
"""
from __future__ import annotations

import logging
from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class RiskMonitorAgent(BaseAgent):
    name = "risk_monitor"
    model = "opus"
    daemon = True

    async def execute(self, task: dict) -> AgentResult:
        portfolio = task.get("portfolio", {})
        positions = task.get("positions", portfolio.get("positions", []))
        equity = task.get("equity", portfolio.get("equity", 100000))
        current_drawdown = task.get("current_drawdown", portfolio.get("drawdown", 0))

        risk_config = self._config.get("risk", {})
        max_drawdown = risk_config.get("max_drawdown", -0.10)
        max_position_pct = risk_config.get("max_position_pct", 0.05)

        warnings = []
        critical = []

        # Check 1: Drawdown
        if current_drawdown < max_drawdown:
            critical.append({
                "check": "drawdown",
                "detail": f"Current drawdown {current_drawdown:.1%} exceeds limit {max_drawdown:.1%}",
                "severity": "critical",
            })

        # Check 2: Single-stock exposure
        for pos in positions:
            symbol = pos.get("symbol", "")
            weight = pos.get("weight", 0)
            value = pos.get("value", 0)
            pct = weight if weight else (value / equity if equity > 0 else 0)

            if pct > 0.10:
                warnings.append({
                    "check": "single_stock_exposure",
                    "symbol": symbol,
                    "detail": f"{symbol} is {pct:.1%} of portfolio (>10%)",
                    "severity": "high",
                })

        # Check 3: Sector concentration
        sector_weights = {}
        for pos in positions:
            sector = pos.get("sector", "unknown")
            weight = pos.get("weight", 0)
            sector_weights[sector] = sector_weights.get(sector, 0) + weight

        for sector, weight in sector_weights.items():
            if weight > 0.40:
                warnings.append({
                    "check": "sector_concentration",
                    "sector": sector,
                    "detail": f"{sector} sector is {weight:.1%} of portfolio (>40%)",
                    "severity": "high",
                })

        # Check 4: Diversification
        num_positions = len(positions)
        if num_positions > 0 and num_positions < 3:
            warnings.append({
                "check": "underdiversified",
                "detail": f"Only {num_positions} positions — consider diversifying",
                "severity": "medium",
            })
        elif num_positions > 50:
            warnings.append({
                "check": "overdiversified",
                "detail": f"{num_positions} positions — may be over-diversified, increasing costs",
                "severity": "low",
            })

        # Check 5: Total exposure
        total_weight = sum(pos.get("weight", 0) for pos in positions)
        if total_weight > 1.0:
            warnings.append({
                "check": "leveraged",
                "detail": f"Total exposure {total_weight:.1%} (>100%) — portfolio is leveraged",
                "severity": "high",
            })

        all_issues = critical + warnings
        risk_level = "critical" if critical else "high" if warnings else "low"

        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "risk_level": risk_level,
                "issues": all_issues,
                "checks_run": 5,
                "num_positions": num_positions,
                "total_exposure": round(total_weight, 2) if positions else 0,
                "current_drawdown": current_drawdown,
                "sector_weights": sector_weights if sector_weights else {},
            },
        )
