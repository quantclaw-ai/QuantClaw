"""Workflow templates — match CEO messages to predefined DAGs without LLM."""
from __future__ import annotations

import re
import uuid
from quantclaw.execution.plan import Plan, PlanStep, StepStatus


WORKFLOW_TEMPLATES = {
    "factor_discovery": {
        "match": ["factor", "alpha", "signal", "find.*strateg", "discover"],
        "phases": [
            {"agent": "researcher", "task": "search_approaches", "depends": []},
            {"agent": "ingestor", "task": "fetch_data", "depends": []},
            {"agent": "miner", "task": "discover_factors", "depends": [0, 1]},
            {"agent": "trainer", "task": "train_model", "depends": [2]},
            # Validator runs in-sample + held-out + verdict in one step.
            {"agent": "validator", "task": "validate", "depends": [3]},
            {"agent": "reporter", "task": "summarize", "depends": [4]},
        ],
        "max_iterations": 3,
    },
    "strategy_backtest": {
        "match": ["backtest", "test.*strateg", "evaluate.*strateg"],
        "phases": [
            {"agent": "ingestor", "task": "fetch_data", "depends": []},
            # Use validator's backtest-only mode when the user just wants a replay.
            {"agent": "validator", "task": "backtest", "depends": [0]},
            {"agent": "reporter", "task": "summarize", "depends": [1]},
        ],
        "max_iterations": 1,
    },
    "market_research": {
        "match": ["research", "analyze.*market", "what.*happening", "news"],
        "phases": [
            {"agent": "researcher", "task": "search", "depends": []},
            {"agent": "reporter", "task": "summarize", "depends": [0]},
        ],
        "max_iterations": 0,
    },
    "risk_check": {
        "match": ["risk", "exposure", "drawdown", "portfolio.*check"],
        "phases": [
            {"agent": "risk_monitor", "task": "check_risk", "depends": []},
            {"agent": "compliance", "task": "check_rules", "depends": []},
            {"agent": "reporter", "task": "summarize", "depends": [0, 1]},
        ],
        "max_iterations": 0,
    },
    "model_training": {
        "match": ["train.*model", "ml.*pipeline", "machine.*learn"],
        "phases": [
            {"agent": "researcher", "task": "search_models", "depends": []},
            {"agent": "ingestor", "task": "fetch_data", "depends": []},
            {"agent": "trainer", "task": "train_model", "depends": [0, 1]},
            {"agent": "validator", "task": "validate", "depends": [2]},
            {"agent": "reporter", "task": "summarize", "depends": [3]},
        ],
        "max_iterations": 3,
    },
    "go_live": {
        "match": ["paper.*trade", "live.*trade", "go.*live", "deploy"],
        "phases": [
            {"agent": "compliance", "task": "check_rules", "depends": []},
            {"agent": "risk_monitor", "task": "check_risk", "depends": []},
            {"agent": "executor", "task": "submit_orders", "depends": [0, 1]},
            {"agent": "reporter", "task": "confirm", "depends": [2]},
        ],
        "max_iterations": 0,
    },
    "refine_factors": {
        "match": ["refine.*factor", "improve.*factor", "better.*factor", "tweak"],
        "phases": [
            {"agent": "miner", "task": "refine_factors", "depends": []},
            {"agent": "trainer", "task": "train_model", "depends": [0]},
            {"agent": "validator", "task": "validate", "depends": [1]},
            {"agent": "reporter", "task": "summarize", "depends": [2]},
        ],
        "max_iterations": 3,
    },
    "apply_new_model": {
        "match": ["try.*model", "different.*model", "switch.*model", "compare.*model"],
        "phases": [
            {"agent": "researcher", "task": "search_models", "depends": []},
            {"agent": "trainer", "task": "train_model", "depends": [0]},
            {"agent": "validator", "task": "validate", "depends": [1]},
            {"agent": "reporter", "task": "summarize", "depends": [2]},
        ],
        "max_iterations": 3,
    },
}


def match_workflow(message: str) -> dict | None:
    """Match a CEO message to a workflow template. Code-only, no LLM."""
    lower = message.lower()
    for name, template in WORKFLOW_TEMPLATES.items():
        if any(re.search(pattern, lower) for pattern in template["match"]):
            return {"name": name, **template}
    return None


DEFAULT_UNIVERSE = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AMD"]

# Default task parameters per agent — enriches template tasks with
# the parameters each agent actually needs
AGENT_TASK_DEFAULTS: dict[str, dict] = {
    "ingestor": {
        "symbols": DEFAULT_UNIVERSE,
    },
    "miner": {
        "symbols": DEFAULT_UNIVERSE,
        "generations": 3,
    },
    "trainer": {
        "model_type": "gradient_boosting",
        "symbols": DEFAULT_UNIVERSE,
        "forward_period": 5,
    },
    "validator": {
        "symbols": DEFAULT_UNIVERSE,
    },
    "researcher": {"task": "search_factors"},
    "reporter": {"task": "summarize"},
}


def plan_from_template(template: dict, goal: str) -> Plan:
    """Build a Plan from a workflow template with sensible defaults."""
    steps = []
    for i, phase in enumerate(template["phases"]):
        # Start with agent-specific defaults, then overlay phase task
        task = {**AGENT_TASK_DEFAULTS.get(phase["agent"], {})}
        task["task"] = phase["task"]
        task["goal"] = goal

        steps.append(PlanStep(
            id=i,
            agent=phase["agent"],
            task=task,
            description=f"{phase['agent']}: {phase['task']}",
            depends_on=phase.get("depends", []),
            status=StepStatus.APPROVED,
        ))
    return Plan(
        id=str(uuid.uuid4())[:8],
        description=goal,
        steps=steps,
    )
