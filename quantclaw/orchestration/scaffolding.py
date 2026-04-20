"""Scaffolding A/B testing — measure which components are still load-bearing.

Components are split into never-skip (security) and testable tiers.
One testable component is randomly disabled per cycle, outcomes tracked
in Playbook for data-driven evidence.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Components that should NEVER be disabled (security/correctness)
NEVER_SKIP = frozenset({
    "ast_validation",
    "sandbox_enforcement",
    "statistical_validation",
    "compliance_veto",
    "contract_floors",
    "held_out_evaluator",
})

# Components that can safely be A/B tested
TESTABLE = {
    "workflow_templates": {
        "description": "Skip template matching, force LLM Planner for all requests",
        "skip_method": "set ooda._skip_templates = True",
    },
    "factor_validation": {
        "description": "Skip AST pre-validation of factor code, let sandbox catch errors",
        "skip_method": "set trainer._skip_factor_validation = True",
    },
    "agent_manifest_in_prompts": {
        "description": "Strip agent manifest from LLM system prompts",
        "skip_method": "set agent._skip_manifest = True",
    },
    "planner_task_schema": {
        "description": "Remove task schema reference from Planner prompt",
        "skip_method": "set planner._skip_schema = True",
    },
}


@dataclass
class ExperimentResult:
    component: str
    disabled: bool
    cycle_sharpe: float
    cycle_errors: int
    cycle_trades: int
    llm_calls: int


def pick_experiment(config: dict) -> str | None:
    """Pick one testable component to disable this cycle, or None."""
    exp_cfg = config.get("scaffolding_experiments", {})
    if not exp_cfg.get("enabled", False):
        return None

    allowed = exp_cfg.get("components", [])
    if not allowed:
        # Default: test all testable components
        allowed = list(TESTABLE.keys())

    valid = [c for c in allowed if c in TESTABLE and c not in NEVER_SKIP]
    if not valid:
        return None

    return random.choice(valid)


def apply_experiment(component: str, ooda) -> bool:
    """Apply a scaffolding experiment by disabling one component.

    Returns True if successfully applied.
    """
    if component == "workflow_templates":
        ooda._skip_templates = True
        logger.info("Scaffolding experiment: skipping workflow templates")
        return True

    if component == "factor_validation":
        # The Trainer's _validate_factor_code will be bypassed
        ooda._skip_factor_validation = True
        logger.info("Scaffolding experiment: skipping factor AST validation")
        return True

    if component == "agent_manifest_in_prompts":
        ooda._skip_manifest = True
        logger.info("Scaffolding experiment: stripping manifest from prompts")
        return True

    if component == "planner_task_schema":
        ooda._skip_task_schema = True
        logger.info("Scaffolding experiment: removing task schema from Planner")
        return True

    return False


def revert_experiment(component: str, ooda) -> None:
    """Revert a scaffolding experiment after cycle completes."""
    if component == "workflow_templates":
        ooda._skip_templates = False
    elif component == "factor_validation":
        ooda._skip_factor_validation = False
    elif component == "agent_manifest_in_prompts":
        ooda._skip_manifest = False
    elif component == "planner_task_schema":
        ooda._skip_task_schema = False
