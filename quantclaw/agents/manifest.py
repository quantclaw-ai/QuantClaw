"""Agent manifest — single source of truth for agent capabilities.

Every agent can query this to understand the full system: who exists,
what they need, what they produce, and when to collaborate.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    uses_llm: bool
    daemon: bool
    inputs: list[str]
    outputs: list[str]
    depends_on: list[str] = field(default_factory=list)
    feeds_into: list[str] = field(default_factory=list)
    task_schema: dict = field(default_factory=dict)


AGENT_MANIFEST: dict[str, AgentSpec] = {
    "researcher": AgentSpec(
        name="researcher",
        description=(
            "Searches the web and synthesizes findings into structured "
            "recommendations for factor discovery and model selection. "
            "Has autonomous web search — decides what to search."
        ),
        uses_llm=True,
        daemon=False,
        inputs=["topic", "task_type", "context"],
        outputs=["findings", "suggested_factors", "suggested_models", "suggested_data_sources"],
        depends_on=[],
        feeds_into=["miner", "trainer", "ingestor"],
        task_schema={
            "topic": "str — research topic",
            "task": "str — e.g. 'search_factors', 'search_models'",
        },
    ),
    "ingestor": AgentSpec(
        name="ingestor",
        description=(
            "Fetches OHLCV market data and additional fields (fundamentals, "
            "sentiment, technical) via data plugins. Can also run web searches "
            "for market intelligence. Dynamically fetches extra fields "
            "suggested by the Researcher."
        ),
        uses_llm=False,
        daemon=False,
        inputs=["symbols", "start", "end", "query", "suggested_data_sources (from upstream)"],
        outputs=["ohlcv (per-symbol row counts)", "columns (list of available DataFrame columns)", "availability (history coverage metadata)", "extra_fields", "search"],
        depends_on=[],
        feeds_into=["miner", "trainer", "validator"],
        task_schema={
            "symbols": "list[str] — e.g. ['AAPL', 'MSFT']",
            "start": "str — date e.g. '2023-01-01'",
            "end": "str — date e.g. '2024-12-31'",
            "query": "str — optional web search query",
        },
    ),
    "miner": AgentSpec(
        name="miner",
        description=(
            "Discovers alpha factors via LLM-powered evolutionary loop. "
            "Generates factor hypotheses as pandas expressions, evaluates "
            "them in the sandbox (IC, Rank IC, Sharpe), then mutates and "
            "crosses over top performers across generations."
        ),
        uses_llm=True,
        daemon=False,
        inputs=["goal", "symbols", "generations", "upstream OHLCV data", "available columns"],
        outputs=["factors (name, hypothesis, code, metrics)", "best_sharpe", "best_ic"],
        depends_on=["ingestor", "researcher"],
        feeds_into=["trainer"],
        task_schema={
            "goal": "str — what kind of factors to find",
            "symbols": "list[str] — universe to evaluate on",
            "generations": "int — number of evolutionary rounds (default 3)",
        },
    ),
    "trainer": AgentSpec(
        name="trainer",
        description=(
            "Trains ML models on factors from the Miner. Generates "
            "executable Strategy class code. Supports sklearn, XGBoost, "
            "LightGBM. All training runs in the sandbox."
        ),
        uses_llm=False,
        daemon=False,
        inputs=["model_type", "symbols", "forward_period", "factors (from upstream miner)"],
        outputs=["model_path", "features_used", "strategy_code", "strategy_path", "sharpe", "metrics"],
        depends_on=["miner"],
        feeds_into=["validator"],
        task_schema={
            "model_type": "str — 'gradient_boosting', 'random_forest', 'xgboost', 'lightgbm', etc.",
            "symbols": "list[str]",
            "forward_period": "int — prediction horizon in days (default 5)",
        },
    ),
    "validator": AgentSpec(
        name="validator",
        description=(
            "Replays strategies in the sandbox and validates them on a held-out "
            "window. Two task modes: 'backtest' runs in-sample replay only; "
            "'validate' (default) runs both in-sample and a held-out backtest "
            "on the last few months the trainer never saw, then returns a "
            "verdict flagging overfit candidates. Code-only, no LLM."
        ),
        uses_llm=False,
        daemon=False,
        inputs=["strategy_code (from upstream)", "symbols", "start", "end", "held_out_months", "task"],
        outputs=[
            "sharpe", "annual_return", "max_drawdown", "total_trades", "win_rate",
            "held_out_sharpe", "held_out_return", "held_out_drawdown",
            "held_out_trades", "degradation_ratio", "verdict", "reason",
        ],
        depends_on=["trainer"],
        feeds_into=["reporter", "executor"],
        task_schema={
            "task": "str — 'validate' (default, full) or 'backtest' (in-sample only)",
            "symbols": "list[str]",
            "start": "str — date range start",
            "end": "str — date range end",
            "held_out_months": "int — size of the held-out window (default from config)",
        },
    ),
    "reporter": AgentSpec(
        name="reporter",
        description=(
            "Summarizes all upstream results into a decision-ready report. "
            "Uses template-based formatting plus a one-paragraph LLM "
            "executive summary. Should be the LAST step in any pipeline."
        ),
        uses_llm=True,
        daemon=False,
        inputs=["_upstream_results from all prior steps"],
        outputs=["report (formatted text)", "summary (LLM paragraph)", "data (raw)"],
        depends_on=["validator", "trainer", "miner", "researcher"],
        feeds_into=[],
        task_schema={"task": "str — 'summarize'"},
    ),
    "executor": AgentSpec(
        name="executor",
        description=(
            "Submits orders. Paper trades by default (tracks cash/positions). "
            "Can also run active paper deployments by loading strategy files, "
            "generating target weights, aggregating them into a paper portfolio, "
            "and submitting rebalancing orders. "
            "Live trading requires trust level >= TRUSTED and a broker plugin. "
            "Compliance veto blocks live trades with violations."
        ),
        uses_llm=False,
        daemon=False,
        inputs=["orders", "strategy_path", "deployments"],
        outputs=["orders_executed", "portfolio (cash, positions, equity)", "deployment_updates"],
        depends_on=["validator", "compliance", "risk_monitor"],
        feeds_into=[],
        task_schema={
            "task": "str — 'submit_orders' or 'run_deployments'",
            "orders": "list[dict] — [{symbol, side, qty, price}]",
            "deployments": "list[dict] — active paper deployment descriptors",
        },
    ),
    "risk_monitor": AgentSpec(
        name="risk_monitor",
        description=(
            "Checks portfolio risk: drawdown, single-stock exposure, "
            "sector concentration, diversification, leverage. Returns "
            "risk_level and list of issues."
        ),
        uses_llm=False,
        daemon=True,
        inputs=["portfolio", "positions", "equity", "current_drawdown"],
        outputs=["risk_level", "issues", "sector_weights", "total_exposure"],
        depends_on=[],
        feeds_into=["executor", "sentinel"],
        task_schema={
            "positions": "list[dict] — [{symbol, weight, value, sector}]",
            "current_drawdown": "float",
        },
    ),
    "compliance": AgentSpec(
        name="compliance",
        description=(
            "Checks trades against rules: position size limits, "
            "drawdown limits, restricted symbols. Returns compliant "
            "boolean and violation details."
        ),
        uses_llm=False,
        daemon=False,
        inputs=["trades", "portfolio_value", "current_drawdown"],
        outputs=["compliant (bool)", "violations"],
        depends_on=[],
        feeds_into=["executor"],
        task_schema={
            "trades": "list[dict] — [{symbol, value}]",
            "portfolio_value": "float",
        },
    ),
    # cost_tracker excluded from manifest — not used in pipelines
    "sentinel": AgentSpec(
        name="sentinel",
        description=(
            "Event-driven safety watchdog. Monitors EventBus for alert "
            "patterns: agent failure streaks, drawdown breaches, cost "
            "warnings, market gaps. Fires alerts to chat."
        ),
        uses_llm=False,
        daemon=True,
        inputs=["EventBus event stream"],
        outputs=["active_rules", "alerts_fired", "failure_counts"],
        depends_on=[],
        feeds_into=[],
        task_schema={},
    ),
    "debugger": AgentSpec(
        name="debugger",
        description=(
            "Diagnoses pipeline errors using LLM. Only used when a "
            "specific agent has failed with a specific error — never "
            "as a first step or for broad goals."
        ),
        uses_llm=True,
        daemon=False,
        inputs=["error", "context", "agent_name", "stack_trace"],
        outputs=["diagnosis", "error_type", "suggestions", "recoverable", "retry_with"],
        depends_on=[],
        feeds_into=[],
        task_schema={
            "error": "str — the error message",
            "agent": "str — which agent failed",
            "context": "str — what was being attempted",
        },
    ),
    "scheduler": AgentSpec(
        name="scheduler",
        description="Cron event loop coordinator. Fires scheduled tasks.",
        uses_llm=False,
        daemon=True,
        inputs=[],
        outputs=[],
        depends_on=[],
        feeds_into=[],
        task_schema={},
    ),
}


def get_manifest() -> dict[str, AgentSpec]:
    """Return the full agent manifest."""
    return dict(AGENT_MANIFEST)


def get_spec(agent_name: str) -> AgentSpec | None:
    """Get spec for a single agent."""
    return AGENT_MANIFEST.get(agent_name)


def get_peers(agent_name: str) -> dict[str, AgentSpec]:
    """Get agents that this agent collaborates with (depends_on + feeds_into)."""
    spec = AGENT_MANIFEST.get(agent_name)
    if not spec:
        return {}
    related = set(spec.depends_on) | set(spec.feeds_into)
    return {name: s for name, s in AGENT_MANIFEST.items() if name in related}


def format_manifest_for_prompt(agent_name: str | None = None) -> str:
    """Format the manifest as text for inclusion in LLM prompts.

    If agent_name is provided, highlights that agent's position in
    the system and emphasizes its direct collaborators.
    """
    lines = ["SYSTEM AGENTS AND CAPABILITIES:"]

    for name, spec in AGENT_MANIFEST.items():
        if name == "scheduler":
            continue  # Internal, not useful for agents to know

        marker = " <-- YOU" if name == agent_name else ""
        llm_tag = " [LLM]" if spec.uses_llm else " [code-only]"
        daemon_tag = " [daemon]" if spec.daemon else ""

        lines.append(f"\n{name}{llm_tag}{daemon_tag}{marker}")
        lines.append(f"  {spec.description}")
        if spec.inputs:
            lines.append(f"  Needs: {', '.join(spec.inputs)}")
        if spec.outputs:
            lines.append(f"  Produces: {', '.join(spec.outputs)}")
        if spec.depends_on:
            lines.append(f"  Runs after: {', '.join(spec.depends_on)}")
        if spec.feeds_into:
            lines.append(f"  Feeds into: {', '.join(spec.feeds_into)}")

    return "\n".join(lines)
