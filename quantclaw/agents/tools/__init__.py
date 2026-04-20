"""Purpose-built domain tools for agents."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class Tool:
    name: str
    description: str
    agent: str  # Which agent this tool belongs to
    handler: Callable[..., Any] | None = None

    async def execute(self, **kwargs) -> dict:
        if self.handler:
            result = self.handler(**kwargs)
            if hasattr(result, '__await__'):
                result = await result
            return {"tool": self.name, "result": result}
        return {"tool": self.name, "result": "not implemented"}


class ToolRegistry:
    """Registry of purpose-built tools available to agents."""

    def __init__(self):
        self._tools: dict[str, list[Tool]] = {}

    def register(self, tool: Tool):
        if tool.agent not in self._tools:
            self._tools[tool.agent] = []
        self._tools[tool.agent].append(tool)

    def get_tools(self, agent_name: str) -> list[Tool]:
        return self._tools.get(agent_name, [])

    def get_tool(self, agent_name: str, tool_name: str) -> Tool | None:
        for tool in self.get_tools(agent_name):
            if tool.name == tool_name:
                return tool
        return None

    def list_all(self) -> dict[str, list[str]]:
        return {agent: [t.name for t in tools] for agent, tools in self._tools.items()}


def create_default_registry() -> ToolRegistry:
    """Create the default tool registry with all built-in tools."""
    registry = ToolRegistry()

    # Ingestor tools
    registry.register(Tool(
        name="check_data_gaps",
        description="Scan for missing dates or symbols in market data",
        agent="ingestor",
    ))
    registry.register(Tool(
        name="validate_data_quality",
        description="Check for outliers, stale prices, and corporate actions",
        agent="ingestor",
    ))
    registry.register(Tool(
        name="fetch_ohlcv",
        description="Fetch OHLCV data for a symbol via the active data plugin",
        agent="ingestor",
    ))

    # Validator tools
    registry.register(Tool(
        name="run_backtest",
        description="Execute a strategy through the active backtest engine",
        agent="validator",
    ))
    registry.register(Tool(
        name="compare_strategies",
        description="Run multiple strategies and compare results side-by-side",
        agent="validator",
    ))
    registry.register(Tool(
        name="get_audit_trail",
        description="Get event-by-event audit trail from a backtest",
        agent="validator",
    ))
    registry.register(Tool(
        name="validate_held_out",
        description="Replay the strategy on a held-out window and return a verdict",
        agent="validator",
    ))

    # Miner tools
    registry.register(Tool(
        name="generate_factor",
        description="Generate a factor formula from a description using LLM",
        agent="miner",
    ))
    registry.register(Tool(
        name="evaluate_factor_ic",
        description="Compute information coefficient for a factor",
        agent="miner",
    ))
    registry.register(Tool(
        name="check_leakage",
        description="Scan factor code for look-ahead bias patterns",
        agent="miner",
    ))

    # Researcher tools
    registry.register(Tool(
        name="search_papers",
        description="Search SSRN and arXiv q-fin for relevant papers",
        agent="researcher",
    ))
    registry.register(Tool(
        name="screen_stocks",
        description="Screen stocks by fundamental or technical criteria",
        agent="researcher",
    ))
    registry.register(Tool(
        name="analyze_correlation",
        description="Compute correlation between two assets or strategies",
        agent="researcher",
    ))

    # Executor tools
    registry.register(Tool(
        name="check_market_hours",
        description="Check if the market is currently open",
        agent="executor",
    ))
    registry.register(Tool(
        name="validate_order",
        description="Validate an order against risk limits before submission",
        agent="executor",
    ))
    registry.register(Tool(
        name="reconcile_positions",
        description="Compare expected vs actual broker positions",
        agent="executor",
    ))

    # Risk Monitor tools
    registry.register(Tool(
        name="compute_realtime_pnl",
        description="Calculate real-time portfolio P&L",
        agent="risk_monitor",
    ))
    registry.register(Tool(
        name="check_drawdown",
        description="Check current drawdown vs configured limits",
        agent="risk_monitor",
    ))
    registry.register(Tool(
        name="scan_gap_events",
        description="Check for overnight gap events in held positions",
        agent="risk_monitor",
    ))

    # Reporter tools
    registry.register(Tool(
        name="generate_equity_chart",
        description="Generate an equity curve chart from backtest results",
        agent="reporter",
    ))
    registry.register(Tool(
        name="generate_comparison_table",
        description="Create a formatted comparison table of strategy metrics",
        agent="reporter",
    ))
    registry.register(Tool(
        name="compute_factor_decay",
        description="Track factor IC decay over time",
        agent="reporter",
    ))

    return registry
