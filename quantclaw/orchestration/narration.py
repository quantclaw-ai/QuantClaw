"""Programmatic narration — format agent results as text without LLM calls."""
from __future__ import annotations

from quantclaw.agents.base import AgentResult


def narrate_step(agent: str, result: AgentResult) -> str:
    """Format step result as narrative text. No LLM call."""
    data = result.data

    if agent == "validator" and data.get("verdict"):
        verdict = data.get("verdict", "unknown")
        held_out = data.get("held_out_sharpe", 0)
        degradation = data.get("degradation_ratio", 0)
        reason = data.get("reason", "")
        if verdict == "validated":
            return f"Validated: held-out Sharpe {held_out:.2f} ({degradation:.0%} of in-sample). {reason}"
        return f"Validation: {verdict}. {reason}"

    if agent == "validator" and "sharpe" in data:
        return (
            f"Backtest complete: Sharpe {data['sharpe']:.2f}, "
            f"annual return {data.get('annual_return', 0):.1%}, "
            f"max drawdown {data.get('max_drawdown', 0):.1%}"
        )

    if agent == "miner" and "factors" in data:
        n = len(data["factors"])
        best = max(
            (f.get("metrics", {}).get("sharpe", 0) for f in data["factors"]),
            default=0,
        )
        return f"Discovered {n} factor{'s' if n != 1 else ''}. Best Sharpe: {best:.2f}"

    if agent == "trainer" and "model_type" in data:
        return (
            f"Trained {data['model_type']} model. "
            f"Test Sharpe: {data.get('sharpe', 0):.2f}, "
            f"overfit ratio: {data.get('metrics', {}).get('overfit_ratio', 0):.2f}"
        )

    if agent == "researcher" and "findings" in data:
        n = len(data["findings"])
        return f"Found {n} relevant finding{'s' if n != 1 else ''}"

    if agent == "ingestor" and "ohlcv" in data:
        successes = sum(
            1 for item in data["ohlcv"].values()
            if isinstance(item, dict) and "rows" in item
        )
        failures = sum(
            1 for item in data["ohlcv"].values()
            if isinstance(item, dict) and "error" in item
        )
        if failures:
            return (
                f"Fetched data for {successes} symbol{'s' if successes != 1 else ''} "
                f"({failures} failed)"
            )
        return f"Fetched data for {successes} symbol{'s' if successes != 1 else ''}"

    if agent == "compliance" and "violations" in data:
        n = len(data["violations"])
        compliant = data.get("compliant", True)
        return f"Compliance: {'PASS' if compliant else f'FAIL ({n} violations)'}"

    if agent == "executor":
        if data.get("deployment_updates"):
            n = len([u for u in data.get("deployment_updates", []) if u.get("status") == "ok"])
            return f"Ran {n} paper deployment{'s' if n != 1 else ''}. Orders executed: {data.get('orders_executed', 0)}"
        orders = data.get("orders", [])
        n = len(orders)
        mode = "paper" if data.get("paper_mode", True) else "live"
        if n > 0:
            return f"Executed {n} orders ({mode} mode)"
        return "No orders to execute"

    if agent == "reporter":
        summary = data.get("summary", "")
        if summary:
            return summary
        return "Report generated"

    if agent == "debugger":
        diagnosis = data.get("diagnosis", "")
        preview = diagnosis[:100] if diagnosis else "No diagnosis"
        return f"Diagnosis: {preview}"

    if agent == "sentinel":
        n_rules = len(data.get("rules", []))
        n_alerts = len(data.get("alerts", []))
        return f"Monitoring: {n_rules} active rules, {n_alerts} alerts"

    if agent == "risk_monitor":
        return "Risk check complete"

    return f"{agent} completed"


def narrate_error(agent: str, result: AgentResult) -> str:
    """Format step failure as narrative text."""
    error = result.error[:200] if result.error else "Unknown error"

    if agent == "trainer":
        return f"Training failed: {error}"
    if agent == "validator":
        return f"Validation failed: {error}"
    if agent == "miner":
        return f"Factor mining failed: {error}"
    if agent == "executor":
        return f"Trade execution failed: {error}"
    if agent == "compliance":
        return f"Compliance check failed: {error}"

    return f"{agent} failed: {error}"
