"""OODA Loop: Observe-Orient-Decide-Act-Learn-Sleep orchestration engine."""
from __future__ import annotations

import asyncio
import json
import uuid
from enum import StrEnum
from typing import Any

from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.orchestration.campaigns import CampaignManager, CampaignPhase, ProfitCampaign
from quantclaw.orchestration.deployments import DeploymentAllocator
from quantclaw.orchestration.playbook import Playbook, EntryType
from quantclaw.orchestration.trust import TrustManager
from quantclaw.agents.base import AgentStatus
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.plan import Plan, PlanStep, PlanStatus, StepStatus
from quantclaw.execution.planner import Planner
from quantclaw.execution.router import LLMRouter


# Known workflow types the Scheduler can draw from
WORKFLOW_EXAMPLES = [
    "signal_hunting", "strategy_development", "backtest_and_compare",
    "go_live", "portfolio_management", "risk_response",
    "research_report", "ml_pipeline",
]


class OODAPhase(StrEnum):
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"
    LEARN = "learn"
    SLEEP = "sleep"


class OODALoop:
    """Continuous OODA loop for the Scheduler agent.

    - decide() uses the LLM via Planner to generate task DAGs
    - act() executes the DAG via Dispatcher
    - sleep_until_trigger() wakes on events, not just timer
    - Playbook context injected into LLM prompts
    """

    def __init__(
        self,
        bus: EventBus,
        playbook: Playbook,
        trust: TrustManager,
        autonomy: AutonomyManager,
        dispatcher: Dispatcher,
        config: dict,
    ):
        self._bus = bus
        self._playbook = playbook
        self._trust = trust
        self._autonomy = autonomy
        self._dispatcher = dispatcher
        self._config = config
        self._phase = OODAPhase.SLEEP
        self._pending_tasks: list[dict] = []
        self._goal: str = ""
        self._wake_event = asyncio.Event()
        self._cycle_count = 0
        self._iteration_context: list[dict] = []
        self._llm_call_count = 0
        self._model_overrides: dict[str, str] = {}  # agent_name → model_id
        self._override_provider: str = ""  # provider for overrides
        self._override_default_model: str = ""  # default model when no per-agent override
        self._cycle_lock = asyncio.Lock()  # Prevents double-fire
        self._current_contract: dict = {}
        self._campaign_manager = CampaignManager(playbook, config)
        self._campaign: ProfitCampaign | None = None
        self._deployment_allocator = DeploymentAllocator(playbook, config)

        # Scaffolding experiment flags
        self._skip_templates = False
        self._skip_factor_validation = False
        self._skip_manifest = False
        self._skip_task_schema = False

        # Wire daemon agents to event bus
        self._sentinel = None
        self._risk_monitor = None
        if hasattr(self._dispatcher, '_pool'):
            sentinel = self._dispatcher._pool.get("sentinel")
            if sentinel:
                self._sentinel = sentinel
                self._bus.subscribe("agent.*", sentinel.on_event)
                self._bus.subscribe("trade.*", sentinel.on_event)
                self._bus.subscribe("cost.*", sentinel.on_event)
                self._bus.subscribe("market.*", sentinel.on_event)

        # Subscribe to wake triggers
        self._bus.subscribe("agent.*", self._on_wake_trigger)
        self._bus.subscribe("market.*", self._on_wake_trigger)

    def set_model_overrides(self, agent_models: dict[str, str], provider: str = "",
                            default_model: str = "", api_key: str = "") -> None:
        """Override model assignments from user's frontend selection.

        agent_models: per-agent assignments from Agents tab (e.g. {"miner": "claude-opus-4-6"})
        provider: the provider for these models (e.g. "anthropic")
        default_model: if set, use this model for all agents without a specific override
        api_key: API key from frontend localStorage or OAuth
        """
        self._model_overrides = agent_models
        self._override_provider = provider
        self._override_default_model = default_model

        # Pass API key or OAuth token through config so LLMRouter can use it
        if api_key:
            # Check if this is an OAuth token (not a standard API key)
            # OAuth tokens are typically longer and don't start with sk-
            is_oauth = api_key and not api_key.startswith("sk-")
            if is_oauth:
                self._config["oauth_token"] = api_key
                self._config.pop("api_key", None)
            else:
                self._config["api_key"] = api_key
                self._config.pop("oauth_token", None)

        # Apply overrides to config so LLMRouter sees them
        if agent_models:
            for agent_name, model_id in agent_models.items():
                self._config.setdefault("models", {})[agent_name] = model_id

        if default_model:
            prov = provider if provider != "ollama" else "ollama"
            self._config.setdefault("providers", {})["user_selected"] = {
                "provider": prov,
                "model": default_model,
            }
            # Override ALL agents to use user_selected
            for agent_name in list(self._config.get("models", {}).keys()):
                if agent_name not in agent_models:
                    self._config["models"][agent_name] = "user_selected"
            # Also set planner explicitly (may not be in models dict)
            self._config.setdefault("models", {})["planner"] = "user_selected"
            self._config.setdefault("models", {})["scheduler"] = "user_selected"

        import logging
        logging.getLogger(__name__).info(
            "Model overrides applied: provider=%s, model=%s, models=%s, providers.user_selected=%s",
            provider, default_model,
            self._config.get("models", {}).get("planner"),
            self._config.get("providers", {}).get("user_selected"),
        )

    async def _on_wake_trigger(self, event: Event) -> None:
        """Wake the OODA loop when a relevant event arrives."""
        self._wake_event.set()

    @property
    def phase(self) -> OODAPhase:
        return self._phase

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def campaign(self) -> ProfitCampaign | None:
        return self._campaign

    def set_goal(self, goal: str) -> None:
        self._goal = goal
        self._campaign = self._campaign_manager.activate(goal, existing=self._campaign)
        if (
            self._campaign
            and self._config.get("campaigns", {}).get("auto_activate_autopilot", True)
        ):
            self._autonomy.set_mode(AutonomyMode.AUTOPILOT)
        self._wake_event.set()

    async def set_goal_persistent(self, goal: str) -> None:
        """Set goal and persist to playbook."""
        self._goal = goal
        self._campaign = self._campaign_manager.activate(goal, existing=self._campaign)
        if (
            self._campaign
            and self._config.get("campaigns", {}).get("auto_activate_autopilot", True)
        ):
            await self._autonomy.set_mode_persistent(AutonomyMode.AUTOPILOT)
            await self._campaign_manager.persist(self._campaign)
        self._wake_event.set()
        await self._playbook.add(EntryType.CEO_PREFERENCE, {"goal": goal})
        if self._campaign:
            if self._campaign.total_cycles > 0:
                message = (
                    f"Resuming the profit campaign for '{goal}' at phase "
                    f"'{self._campaign.phase.value}' after {self._campaign.total_cycles} cycles."
                )
            else:
                message = (
                    f"Starting a profit campaign for '{goal}'. "
                    "I will keep iterating through discovery, validation, and paper-trading phases."
                )
            await self._bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={
                    "message": message,
                    "role": "scheduler",
                },
                source_agent="scheduler",
            ))

    @staticmethod
    async def restore_goal(playbook: Playbook) -> str:
        """Restore goal from playbook."""
        entries = await playbook.query(entry_type=EntryType.CEO_PREFERENCE)
        for entry in reversed(entries):
            if "goal" in entry.content:
                return entry.content["goal"]
        return ""

    async def restore_persistent_state(self) -> None:
        """Restore standing goal and campaign state from the playbook."""
        self._goal = await self.restore_goal(self._playbook)
        if self._goal:
            self._campaign = await self._campaign_manager.restore(self._goal)
            self._wake_event.set()

    def _is_single_pass_paper_cycle(self, state: dict) -> bool:
        return bool(
            self._campaign
            and self._campaign.status.value == "active"
            and self._campaign.phase.value == "paper"
            and (state.get("deployments") or {}).get("active_count", 0) > 0
        )

    def add_pending_task(self, task: dict) -> None:
        self._pending_tasks.append(task)
        self._wake_event.set()

    async def _get_exploration_mode(self) -> tuple[str, float]:
        """Determine explore/exploit mode based on Playbook maturity."""
        orch_cfg = self._config.get("orchestration", {})
        explore_cfg = orch_cfg.get("exploration", {})
        high_until = explore_cfg.get("high_explore_until", 5)
        balanced_until = explore_cfg.get("balanced_until", 15)

        all_results = await self._playbook.query(entry_type=EntryType.STRATEGY_RESULT)
        playbook_size = len(all_results)

        if playbook_size < high_until:
            return "explore", explore_cfg.get("explore_temp", 0.7)
        elif playbook_size < balanced_until:
            return "balanced", explore_cfg.get("balanced_temp", 0.4)
        else:
            return "exploit", explore_cfg.get("exploit_temp", 0.2)

    @staticmethod
    def _summarize_cycle_results(results: dict) -> dict:
        best_sharpe = 0.0
        best_result: dict = {}
        best_backtest: dict = {}
        best_model: dict = {}
        evaluator_result: dict = {}
        total_trades = 0
        signal_errors = 0
        sample_size = 0
        paper_orders_executed = 0
        successful_deployments = 0
        failed_deployments = 0
        is_paper_cycle = False

        for result in results.values():
            if result.status != AgentStatus.SUCCESS:
                continue
            data = result.data or {}
            sharpe = float(data.get("sharpe", 0) or 0)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_result = dict(data)

            if "annual_return" in data and "sharpe" in data:
                if sharpe >= float(best_backtest.get("sharpe", 0) or 0):
                    best_backtest = dict(data)
            elif data.get("model_type") and "sharpe" in data:
                if sharpe >= float(best_model.get("sharpe", 0) or 0):
                    best_model = dict(data)

            if (
                "held_out_sharpe" in data
                or "held_out_trades" in data
                or data.get("verdict") in {"validated", "insufficient_trades", "overfit", "no_edge", "below_contract"}
            ):
                evaluator_result = dict(data)

            total_trades += int(data.get("total_trades", 0) or 0)
            signal_errors += int(data.get("signal_errors", 0) or 0)
            sample_size = max(sample_size, int(data.get("sample_size", 0) or 0))

            if "ohlcv" in data:
                for sym_data in data["ohlcv"].values():
                    if isinstance(sym_data, dict) and "rows" in sym_data:
                        sample_size = max(sample_size, int(sym_data["rows"]))

            if data.get("paper_mode") or data.get("mode") == "paper" or "deployment_updates" in data:
                is_paper_cycle = True
                paper_orders_executed += int(data.get("orders_executed", 0) or 0)
                updates = data.get("deployment_updates", [])
                successful_deployments += len(
                    [update for update in updates if update.get("status") == "ok"]
                )
                failed_deployments += len(
                    [update for update in updates if update.get("status") == "failed"]
                )

        merged_result = dict(best_backtest or best_model or best_result or evaluator_result)
        if evaluator_result:
            for key in (
                "verdict",
                "reason",
                "held_out_sharpe",
                "held_out_trades",
                "held_out_return",
                "held_out_drawdown",
                "held_out_win_rate",
                "held_out_period",
                "in_sample_sharpe",
                "degradation_ratio",
            ):
                if key in evaluator_result:
                    merged_result[key] = evaluator_result[key]
            best_sharpe = max(best_sharpe, float(evaluator_result.get("in_sample_sharpe", 0) or 0))

        return {
            "best_sharpe": best_sharpe,
            "best_result": merged_result,
            "total_trades": total_trades,
            "signal_errors": signal_errors,
            "sample_size": sample_size,
            "paper": {
                "is_paper_cycle": is_paper_cycle,
                "orders_executed": paper_orders_executed,
                "successful_deployments": successful_deployments,
                "failed_deployments": failed_deployments,
            },
        }

    async def _evaluate_results(self, results: dict, iteration: int) -> dict:
        """Evaluate cycle results: percentile ranking + LLM judgment."""
        max_iterations = self._config.get(
            "orchestration", {}).get("max_iterations_per_cycle", 3)
        summary = self._summarize_cycle_results(results)
        best_sharpe = summary["best_sharpe"]
        best_result = summary["best_result"]
        total_trades = summary["total_trades"]
        signal_errors = summary["signal_errors"]
        sample_size = summary["sample_size"]
        paper = summary["paper"]

        if paper["is_paper_cycle"]:
            if paper["successful_deployments"] <= 0 and paper["failed_deployments"] > 0:
                evaluation = {
                    "verdict": "abandon" if iteration >= max_iterations else "iterate",
                    "reasoning": (
                        f"Paper deployment runner failed for all active deployments "
                        f"({paper['failed_deployments']} failed)."
                    ),
                    "suggestion": (
                        "Inspect strategy loading, required data fields, and signal generation "
                        "before the next paper cycle."
                    ),
                    "best_result": best_result,
                    "diagnostics": {
                        "issue": "paper_runner_failed",
                        "orders_executed": paper["orders_executed"],
                    },
                }
            elif paper["orders_executed"] > 0:
                evaluation = {
                    "verdict": "pursue",
                    "reasoning": (
                        f"Paper portfolio rebalanced with {paper['orders_executed']} order"
                        f"{'s' if paper['orders_executed'] != 1 else ''} across "
                        f"{paper['successful_deployments']} deployment"
                        f"{'s' if paper['successful_deployments'] != 1 else ''}."
                    ),
                    "suggestion": "Keep monitoring fills, cash usage, and portfolio drift.",
                    "best_result": best_result,
                    "diagnostics": {
                        "issue": "",
                        "orders_executed": paper["orders_executed"],
                    },
                }
            else:
                reason = (
                    "Paper deployment cycle ran but produced no rebalance orders. "
                    "That can be normal if target weights were already aligned, but verify the "
                    "portfolio state and signal freshness."
                )
                suggestion = (
                    "Confirm the active strategies are emitting fresh scores and that the "
                    "paper portfolio has enough free cash for planned rebalances."
                )
                if signal_errors > 0:
                    reason = (
                        f"Paper deployment cycle ran but produced no rebalance orders and "
                        f"reported {signal_errors} signal error"
                        f"{'s' if signal_errors != 1 else ''}."
                    )
                    suggestion = (
                        "Inspect model loading and required feature fields for the active "
                        "deployments before the next paper cycle."
                    )
                evaluation = {
                    "verdict": "iterate",
                    "reasoning": reason,
                    "suggestion": suggestion,
                    "best_result": best_result,
                    "diagnostics": {
                        "issue": "paper_no_orders",
                        "orders_executed": 0,
                    },
                }

            await self._bus.publish(Event(
                type=EventType.ORCHESTRATION_EVALUATION,
                payload={
                    "iteration": iteration,
                    "verdict": evaluation["verdict"],
                    "percentile": None,
                    "results": best_result,
                    "reasoning": evaluation.get("reasoning", ""),
                    "suggestion": evaluation.get("suggestion", ""),
                },
                source_agent="scheduler",
            ))
            return evaluation

        # Zero-trade detection: if strategies produced no trades, this is a
        # technical/signal issue — iterate to fix it rather than abandoning.
        if total_trades == 0 and iteration < max_iterations:
            diag_reason = "Zero trades generated"
            if signal_errors > 0:
                diag_reason += f" ({signal_errors} signal errors — likely model loading or feature calculation failure)"
            else:
                diag_reason += " (signals may be too weak or allocation thresholds too strict)"
            evaluation = {
                "verdict": "iterate",
                "reasoning": diag_reason,
                "suggestion": (
                    "Fix signal generation: verify model loads correctly, "
                    "check feature calculations produce non-NaN values, "
                    "and ensure allocate() returns non-empty weights. "
                    "Try simpler factors or a linear model to confirm the pipeline works."
                ),
                "best_result": best_result,
                "diagnostics": {
                    "total_trades": 0,
                    "signal_errors": signal_errors,
                    "issue": "zero_trades",
                },
            }
            await self._bus.publish(Event(
                type=EventType.ORCHESTRATION_EVALUATION,
                payload={
                    "iteration": iteration,
                    "verdict": evaluation["verdict"],
                    "percentile": None,
                    "results": best_result,
                    "reasoning": evaluation.get("reasoning", ""),
                    "suggestion": evaluation.get("suggestion", ""),
                },
                source_agent="scheduler",
            ))
            return evaluation

        # Step 1: Playbook percentile
        past = await self._playbook.query(entry_type=EntryType.STRATEGY_RESULT)
        past_sharpes = [e.content.get("sharpe", 0) for e in past]

        percentile = None
        percentile_note = "Not enough history for comparison. Evaluate on absolute metrics."
        if len(past_sharpes) >= 3:
            percentile = sum(1 for s in past_sharpes if best_sharpe > s) / len(past_sharpes)
            percentile_note = f"Top {(1 - percentile) * 100:.0f}% of {len(past_sharpes)} past strategies"


        # Step 2: LLM judgment (try, fallback to heuristic)
        try:
            router = LLMRouter(self._config)

            prompt = (
                f"You are evaluating strategy results.\n\n"
                f"Result: {json.dumps(best_result)}\n"
                f"Total trades: {total_trades}, Signal errors: {signal_errors}\n"
                f"Sample size: {sample_size} daily data points\n"
                f"Sprint contract: {json.dumps(self._current_contract)}\n"
                f"Percentile: {percentile_note}\n"
                f"Previous iterations this cycle: {json.dumps(self._iteration_context)}\n"
                f"Iteration {iteration} of {max_iterations}\n\n"
                f"Should we:\n"
                f"- pursue: results are strong enough AND statistically valid\n"
                f"- iterate: promising but could improve, suggest refinement\n"
                f"- abandon: not worth continuing, overfitting detected, or statistically invalid\n\n"
                f"IMPORTANT: If total_trades is 0, this is a pipeline/signal issue, NOT a strategy quality issue. "
                f"Prefer 'iterate' with a suggestion to fix the signal pipeline.\n\n"
                f"{'If this is the last iteration, you MUST choose pursue or abandon.' if iteration >= max_iterations else ''}\n\n"
                f"Respond as JSON: {{\"verdict\": str, \"reasoning\": str, \"suggestion\": str}}"
            )

            # Load calibration rules from Playbook
            calibration_rules = await self._playbook.query(
                entry_type=EntryType.EVALUATOR_CALIBRATION
            )
            calibration_section = ""
            if calibration_rules:
                eval_cfg = self._config.get("evaluator", {})
                max_rules = eval_cfg.get("max_calibration_rules", 10)
                recent = calibration_rules[-max_rules:]
                calibration_section = (
                    "\n\nLEARNED CALIBRATION RULES (from past divergences — apply these):\n"
                    + "\n".join(f"- {r.content.get('rule', '')}" for r in recent)
                )

            response = await router.call(
                "scheduler",
                messages=[{"role": "user", "content": prompt}],
                system=(
                    "You are a quantitative strategy evaluator. Respond only with valid JSON.\n\n"
                    "STATISTICAL VALIDATION — apply these rules before any verdict:\n\n"
                    "A backtest Sharpe ratio is only an estimate of the strategy's true expected "
                    "Sharpe ratio. The estimate is unreliable unless the sample size is sufficient.\n\n"
                    "Minimum sample sizes for 95% confidence that the true Sharpe >= 0:\n"
                    "- Backtest Sharpe ~1.0 → need >= 681 daily data points (~2.7 years)\n"
                    "- Backtest Sharpe ~2.0 → need >= 174 daily data points (~0.7 years)\n"
                    "- Backtest Sharpe >= 3.0 → likely overfitting or data error; flag it\n\n"
                    "For 95% confidence that the true Sharpe >= 1:\n"
                    "- Backtest Sharpe ~1.5 → need >= 2,739 daily data points (~10.9 years)\n\n"
                    "Key rules:\n"
                    "- A Sharpe of 10+ on daily data is almost certainly a bug, data leak, or overfit. "
                    "Never pursue — flag as suspicious.\n"
                    "- Compare the number of data points (sample size) against these thresholds. "
                    "If the sample is too small for the reported Sharpe, the result is unreliable.\n"
                    "- High train Sharpe but low test accuracy (< 55%) suggests the model is "
                    "memorizing noise, not learning signal.\n"
                    "- An overfit_ratio > 2.0 (train_sharpe / test_sharpe) is a red flag.\n"
                    "- These rules also apply to out-of-sample and paper trading evaluation."
                    + calibration_section
                ),
                temperature=0.2,
            )
            self._llm_call_count += 1

            evaluation = json.loads(response)
        except Exception:
            # Heuristic fallback using contract thresholds
            min_sharpe = self._current_contract.get("min_sharpe", 0.0)
            if iteration >= max_iterations:
                verdict = "pursue" if best_sharpe > min_sharpe else "abandon"
            elif best_sharpe > max(1.0, min_sharpe * 2):
                verdict = "pursue"
            elif iteration < max_iterations:
                # Keep iterating until we exhaust attempts — early abandon
                # throws away learning opportunities
                verdict = "iterate"
            else:
                verdict = "abandon"
            evaluation = {
                "verdict": verdict,
                "reasoning": f"Heuristic: sharpe={best_sharpe:.2f}, trades={total_trades}",
                "suggestion": "Try a different approach" if verdict == "abandon" else "Refine parameters",
            }

        evaluation["percentile"] = percentile
        evaluation["best_result"] = best_result

        # Emit evaluation event
        await self._bus.publish(Event(
            type=EventType.ORCHESTRATION_EVALUATION,
            payload={
                "iteration": iteration,
                "verdict": evaluation["verdict"],
                "percentile": percentile,
                "results": best_result,
                "reasoning": evaluation.get("reasoning", ""),
                "suggestion": evaluation.get("suggestion", ""),
            },
            source_agent="scheduler",
        ))

        return evaluation

    async def observe(self) -> dict[str, Any]:
        """OBSERVE: Gather current state from all sources."""
        self._phase = OODAPhase.OBSERVE

        recent_events = self._bus.recent(20)
        playbook_recent = await self._playbook.recent(10)
        deployment_context = None
        if self._campaign:
            deployment_context = await self._deployment_allocator.prompt_context(self._campaign.id)

        return {
            "pending_tasks": list(self._pending_tasks),
            "recent_events": [
                {"type": str(e.type), "payload": e.payload, "source": e.source_agent}
                for e in recent_events
            ],
            "playbook_recent": [
                {"type": e.entry_type.value, "content": e.content, "tags": e.tags}
                for e in playbook_recent
            ],
            "trust_level": self._trust.level.name,
            "trust_metrics": self._trust.get_metrics(),
            "autonomy_mode": self._autonomy.mode.value,
            "campaign": self._campaign.to_prompt_context() if self._campaign else None,
            "deployments": deployment_context,
        }

    async def orient(self, state: dict, goal: str = "") -> dict[str, Any]:
        """ORIENT: Compare current state to goal, determine needed actions."""
        self._phase = OODAPhase.ORIENT

        active_goal = goal or self._goal
        campaign_context = state.get("campaign")
        deployment_context = state.get("deployments")
        if not goal and self._campaign:
            active_goal = self._campaign_manager.next_subgoal(self._campaign, deployment_context)
            campaign_context = self._campaign.to_prompt_context()

        actions_needed: list[str] = []

        if state["pending_tasks"]:
            actions_needed.append("process_pending_tasks")

        market_events = [
            e for e in state["recent_events"]
            if e["type"].startswith("market.")
        ]
        if market_events:
            actions_needed.append("respond_to_market_events")

        if not actions_needed and active_goal:
            actions_needed.append("plan_toward_goal")

        return {
            "goal": active_goal,
            "actions_needed": actions_needed,
            "market_events": market_events,
            "trust_level": state["trust_level"],
            "playbook_context": state["playbook_recent"],
            "campaign_context": campaign_context,
            "deployment_context": deployment_context,
        }

    async def decide(self, orientation: dict) -> Plan | None:
        """DECIDE: Use LLM via Planner to generate a task DAG.

        Calls Planner.create_plan() with goal + playbook context,
        letting the LLM generate the DAG with creative latitude.
        Returns a Plan object, not a plain dict.
        """
        self._phase = OODAPhase.DECIDE

        if not orientation["actions_needed"]:
            return None

        # Try template match first (free, no LLM call) — only on first iteration
        from quantclaw.orchestration.workflows import match_workflow, plan_from_template

        goal = orientation.get("goal", "")
        deployment_context = orientation.get("deployment_context", {})

        if (
            self._campaign
            and self._campaign.phase.value == "paper"
            and deployment_context.get("active_count", 0) > 0
        ):
            plan = self._build_paper_deployment_plan(goal, deployment_context)
            await self._bus.publish(Event(
                type=EventType.ORCHESTRATION_PLAN_CREATED,
                payload={
                    "plan_id": plan.id,
                    "description": plan.description,
                    "steps": len(plan.steps),
                    "source": "paper_deployment_runner",
                },
                source_agent="scheduler",
            ))
            if not self._autonomy.should_wait_for_approval():
                plan.approve_all()
            return plan

        if not self._iteration_context and not self._skip_templates:
            template = match_workflow(goal)
            if template:
                plan = plan_from_template(template, goal)
                # Skip the Planner LLM call entirely
                await self._bus.publish(Event(
                    type=EventType.ORCHESTRATION_PLAN_CREATED,
                    payload={"plan_id": plan.id, "description": plan.description,
                             "steps": len(plan.steps), "source": "template",
                             "template": template.get("name", "")},
                    source_agent="scheduler",
                ))
                # In Autopilot: auto-approve. In Plan Mode: leave as proposed.
                if not self._autonomy.should_wait_for_approval():
                    plan.approve_all()
                return plan

        # Build a rich prompt with playbook context
        playbook_summary = ""
        if orientation.get("playbook_context"):
            entries = orientation["playbook_context"][:5]
            playbook_summary = "\n\nPlaybook context (recent knowledge):\n"
            for e in entries:
                playbook_summary += f"- [{e['type']}] {json.dumps(e['content'])[:200]}\n"

        goal = orientation.get("goal", "")
        actions = ", ".join(orientation["actions_needed"])

        planner_request = (
            f"Goal: {goal}\n"
            f"Actions needed: {actions}\n"
            f"Trust level: {orientation.get('trust_level', 'OBSERVER')}\n"
            f"Known workflow types: {', '.join(WORKFLOW_EXAMPLES)}\n"
            f"You have full creative latitude — invent new approaches, "
            f"try unconventional combinations, run parallel experiments.\n"
            f"Campaign context: {json.dumps(orientation.get('campaign_context', {}))}\n"
            f"Deployment context: {json.dumps(orientation.get('deployment_context', {}))}\n"
            f"{playbook_summary}"
        )

        try:
            router = LLMRouter(self._config)
            planner = Planner(router)
            plan = await planner.create_plan(planner_request, context={
                "playbook_context": orientation.get("playbook_context", []),
                "iteration_context": orientation.get("iteration_context", []),
                "exploration_mode": orientation.get("exploration_mode", ""),
                "exploration_temp": orientation.get("exploration_temp", 0.5),
                "campaign_context": orientation.get("campaign_context", {}),
                "deployment_context": orientation.get("deployment_context", {}),
            })
            self._llm_call_count += 1  # Count the planning LLM call
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("LLM planning failed, using fallback")
            await self._bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={
                    "message": f"Couldn't reach LLM for planning ({e}). Using basic task dispatch.",
                    "role": "scheduler",
                },
                source_agent="scheduler",
            ))
            # Fallback: create a minimal plan from pending tasks
            steps = []
            for i, task in enumerate(self._pending_tasks):
                steps.append(PlanStep(
                    id=i,
                    agent=task.get("agent", "researcher"),
                    task=task.get("task", {}) if isinstance(task.get("task"), dict) else {"task": task.get("task", "")},
                    description=f"Process: {task.get('agent', 'unknown')}",
                    depends_on=[],
                ))
            if not steps:
                # No LLM and no pending tasks — can't do anything
                await self._bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={
                        "message": "This goal requires an LLM provider to plan. Install Ollama or set an API key.",
                        "role": "scheduler",
                    },
                    source_agent="scheduler",
                ))
                return None
            plan = Plan(
                id=str(uuid.uuid4())[:8],
                description=goal or "Process pending tasks",
                steps=steps,
            )

        # Auto-approve if: Autopilot mode, OR chat-triggered (CEO explicitly asked)
        if not self._autonomy.should_wait_for_approval() or getattr(self, '_auto_approve', False):
            plan.approve_all()

        await self._bus.publish(Event(
            type=EventType.ORCHESTRATION_PLAN_CREATED,
            payload={"plan_id": plan.id, "description": plan.description,
                     "steps": len(plan.steps)},
            source_agent="scheduler",
        ))

        return plan

    async def act(self, plan: Plan) -> dict:
        """ACT: Execute the plan DAG via Dispatcher."""
        self._phase = OODAPhase.ACT

        plan.status = PlanStatus.EXECUTING
        results = await self._dispatcher.execute_plan(plan)

        # Clear pending tasks that were incorporated into this plan
        self._pending_tasks.clear()

        return results

    async def learn(self, result: dict) -> None:
        """LEARN: Record outcomes to playbook."""
        self._phase = OODAPhase.LEARN

        entry_type = EntryType(result.get("type", "strategy_result"))
        content = result.get("content", {})
        tags = result.get("tags", [])

        entry = await self._playbook.add(entry_type, content, tags)

        await self._bus.publish(Event(
            type=EventType.PLAYBOOK_ENTRY_ADDED,
            payload={
                "entry_type": entry.entry_type.value,
                "tags": entry.tags,
            },
            source_agent="scheduler",
        ))

        # Check if trust level should be auto-upgraded based on trade history
        await self._trust.check_auto_upgrade()

    async def run_cycle(self, chat_history: list[dict] | None = None,
                        auto_approve: bool = False) -> dict | None:
        """Run a single OODA cycle with iterative evaluation.

        The evaluate -> decide -> act loop can repeat up to max_iterations_per_cycle.
        Uses _cycle_lock to prevent double-fire from chat endpoint + run_continuous.

        auto_approve: if True, auto-approve all plan steps regardless of autonomy mode.
                      Used for chat-triggered cycles (CEO explicitly asked for this).
        """
        async with self._cycle_lock:
            return await self._run_cycle_inner(chat_history, auto_approve)

    async def _run_cycle_inner(self, chat_history: list[dict] | None = None,
                               auto_approve: bool = False) -> dict | None:
        self._auto_approve = auto_approve
        self._iteration_context = []
        self._llm_call_count = 0

        # Scaffolding A/B test: optionally disable one component
        from quantclaw.orchestration.scaffolding import pick_experiment, apply_experiment, revert_experiment
        experiment_component = pick_experiment(self._config)
        if experiment_component:
            apply_experiment(experiment_component, self)

        # Get exploration mode
        exploration_mode, exploration_temp = await self._get_exploration_mode()

        # Observe
        state = await self.observe()
        if chat_history:
            max_history = self._config.get("orchestration", {}).get("max_chat_history", 10)
            state["chat_history"] = chat_history[-max_history:]
        max_iterations = 1 if self._is_single_pass_paper_cycle(state) else (
            self._config.get("orchestration", {}).get("max_iterations_per_cycle", 3)
        )

        best_results = None
        best_evaluation = None

        for iteration in range(1, max_iterations + 1):
            # Orient
            orientation = await self.orient(state)

            # Inject iteration context
            if self._iteration_context:
                orientation["iteration_context"] = self._iteration_context
            orientation["exploration_mode"] = exploration_mode
            orientation["exploration_temp"] = exploration_temp

            # Decide
            plan = await self.decide(orientation)
            if plan is None:
                break

            if plan and plan.contract:
                self._current_contract = plan.contract

            # Act
            results = await self.act(plan)

            # Narrate results programmatically (no LLM call)
            from quantclaw.orchestration.narration import narrate_step
            if plan:
                for step in plan.steps:
                    step_result = results.get(step.id)
                    if step_result and step_result.status == AgentStatus.SUCCESS:
                        narrative = narrate_step(step.agent, step_result)
                        await self._bus.publish(Event(
                            type=EventType.CHAT_NARRATIVE,
                            payload={"message": narrative, "role": "scheduler"},
                            source_agent="scheduler",
                        ))
                    elif step_result and step_result.status != AgentStatus.SUCCESS:
                        from quantclaw.orchestration.narration import narrate_error
                        narrative = narrate_error(step.agent, step_result)
                        await self._bus.publish(Event(
                            type=EventType.CHAT_NARRATIVE,
                            payload={"message": narrative, "role": "scheduler"},
                            source_agent="scheduler",
                        ))

            # Evaluate
            evaluation = await self._evaluate_results(results, iteration)
            verdict = evaluation.get("verdict", "pursue")

            # Narrate
            await self._bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={
                    "message": f"Iteration {iteration}: {evaluation.get('reasoning', '')}",
                    "role": "scheduler",
                },
                source_agent="scheduler",
            ))

            if verdict == "pursue":
                best_results = results
                best_evaluation = evaluation
                break
            elif verdict == "iterate" and iteration < max_iterations:
                # Build handoff for next iteration with diagnostics
                avoid_factors = []
                avoid_models = []
                iter_total_trades = 0
                iter_signal_errors = 0
                for step_id, r in results.items():
                    if r.status != AgentStatus.SUCCESS:
                        continue
                    d = r.data
                    if "factors" in d:
                        for f in d["factors"]:
                            avoid_factors.append(f.get("name", ""))
                    if "model_id" in d:
                        avoid_models.append(f"{d.get('model_type', '')} (Sharpe {d.get('sharpe', 0):.2f})")
                    iter_total_trades += d.get("total_trades", 0)
                    iter_signal_errors += d.get("signal_errors", 0)

                iter_best_sharpe = evaluation.get("best_result", {}).get("sharpe", 0)
                diagnostics = evaluation.get("diagnostics", {})
                self._iteration_context.append({
                    "iteration": iteration,
                    "avoid_factors": avoid_factors,
                    "avoid_models": avoid_models,
                    "best_sharpe": iter_best_sharpe,
                    "verdict": verdict,
                    "total_trades": iter_total_trades,
                    "signal_errors": iter_signal_errors,
                    "issue": diagnostics.get("issue", ""),
                    "suggestion": evaluation.get("suggestion", ""),
                })
                # Shift toward exploit for refinement
                exploration_mode = "exploit"
                exploration_temp = self._config.get(
                    "orchestration", {}).get("exploration", {}).get("exploit_temp", 0.2)
                best_results = results
                best_evaluation = evaluation
                continue
            else:
                # abandon or last iteration
                best_results = results
                best_evaluation = evaluation
                break

        if best_results is None:
            await self.sleep()
            return None

        self._cycle_count += 1

        # Learn from best results
        for step_id, result in best_results.items():
            if result.status == AgentStatus.SUCCESS and result.data:
                entry_type = "strategy_result"
                if best_evaluation and best_evaluation.get("verdict") == "abandon":
                    entry_type = "what_failed"
                await self.learn({
                    "type": entry_type,
                    "content": result.data,
                    "tags": ["auto", exploration_mode],
                })

        # Track evaluator divergences for auto-tuning
        if best_evaluation and best_evaluation.get("verdict") == "pursue":
            # Check if the Evaluator agent (held-out backtest) disagreed
            for step_id, result in best_results.items():
                if result.status == AgentStatus.SUCCESS and result.data.get("verdict") in (
                    "overfit", "no_edge", "below_contract"
                ):
                    # Divergence: OODA evaluator said pursue, held-out said fail
                    await self._log_divergence(best_evaluation, result.data)
                    break

        # Run calibration cycle periodically
        eval_cfg = self._config.get("evaluator", {})
        cal_interval = eval_cfg.get("calibration_interval", 5)
        if self._cycle_count > 0 and self._cycle_count % cal_interval == 0:
            await self._run_calibration()

        campaign_update = None
        allocation_update = None
        deployment_context = None
        if self._campaign and best_evaluation:
            campaign_update = await self._campaign_manager.record_cycle(
                self._campaign, best_results, best_evaluation,
            )
            await self._bus.publish(Event(
                type=EventType.ORCHESTRATION_CAMPAIGN_UPDATED,
                payload=self._campaign.to_prompt_context(),
                source_agent="scheduler",
            ))
            allocation_update = await self._deployment_allocator.rebalance(
                self._campaign.id,
                self._cycle_count,
                best_results,
                best_evaluation,
            )
            deployment_context = await self._deployment_allocator.prompt_context(self._campaign.id)
            if allocation_update:
                await self._bus.publish(Event(
                    type=EventType.ORCHESTRATION_ALLOCATION_UPDATED,
                    payload=deployment_context,
                    source_agent="scheduler",
                ))

        # Emit enriched cycle complete
        iterations_done = len(self._iteration_context) + 1
        await self._bus.publish(Event(
            type=EventType.ORCHESTRATION_CYCLE_COMPLETE,
            payload={
                "cycle": self._cycle_count,
                "plan_id": "",
                "iterations": iterations_done,
                "llm_calls": self._llm_call_count,
                "exploration_mode": exploration_mode,
                "temperature": exploration_temp,
                "verdict": best_evaluation.get("verdict", "pursue") if best_evaluation else "none",
                "percentile": best_evaluation.get("percentile") if best_evaluation else None,
                "reasoning": best_evaluation.get("reasoning", "") if best_evaluation else "",
                "steps_completed": len([r for r in best_results.values()
                                         if r.status == AgentStatus.SUCCESS]),
                "campaign_phase": self._campaign.phase.value if self._campaign else "",
                "campaign_goal": self._campaign.root_goal if self._campaign else "",
                "active_deployments": deployment_context.get("active_count", 0) if deployment_context else 0,
            },
            source_agent="scheduler",
        ))

        # Summary narration
        verdict = best_evaluation.get("verdict", "") if best_evaluation else ""
        percentile = best_evaluation.get("percentile") if best_evaluation else None
        pct_str = f"top {(1 - percentile) * 100:.0f}%" if percentile is not None else "no history"

        await self._bus.publish(Event(
            type=EventType.CHAT_NARRATIVE,
            payload={
                "message": (
                    f"Completed {iterations_done} iteration{'s' if iterations_done > 1 else ''}. "
                    f"Verdict: {verdict} ({pct_str}). "
                    f"{self._llm_call_count} LLM calls used."
                ),
                "role": "scheduler",
            },
            source_agent="scheduler",
        ))

        if campaign_update:
            if campaign_update.transition_message:
                await self._bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={
                        "message": campaign_update.transition_message,
                        "role": "scheduler",
                    },
                    source_agent="scheduler",
                ))
            if campaign_update.status_message:
                await self._bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={
                        "message": campaign_update.status_message,
                        "role": "scheduler",
                    },
                    source_agent="scheduler",
                ))
            if campaign_update.checkpoint_message:
                await self._bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={
                        "message": campaign_update.checkpoint_message,
                        "role": "scheduler",
                    },
                    source_agent="scheduler",
                ))
        if allocation_update and allocation_update.message:
            await self._bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={
                    "message": allocation_update.message,
                    "role": "scheduler",
                },
                source_agent="scheduler",
            ))

        # Log scaffolding experiment result
        if experiment_component:
            revert_experiment(experiment_component, self)
            exp_sharpe = 0
            exp_errors = 0
            exp_trades = 0
            if best_results:
                for r in best_results.values():
                    if r.status == AgentStatus.SUCCESS:
                        exp_sharpe = max(exp_sharpe, r.data.get("sharpe", 0))
                        exp_trades += r.data.get("total_trades", 0)
                    else:
                        exp_errors += 1

            await self._playbook.add(
                EntryType.SCAFFOLDING_EXPERIMENT,
                {
                    "component": experiment_component,
                    "disabled": True,
                    "cycle_sharpe": exp_sharpe,
                    "cycle_errors": exp_errors,
                    "cycle_trades": exp_trades,
                    "llm_calls": self._llm_call_count,
                },
                tags=["auto", "experiment"],
            )

        self._iteration_context = []
        await self.sleep()
        return best_results

    def _build_paper_deployment_plan(self, goal: str, deployment_context: dict) -> Plan:
        """Build the cycle plan for paper phase.

        Default plan: run the active paper deployments and summarize. On every
        Nth paper cycle (config: ``campaigns.paper_shadow_search_every``) the
        plan ALSO runs a full discovery pipeline in parallel as a "shadow
        search" — looking for a challenger strategy that could displace the
        incumbent. The allocator handles incumbent-vs-challenger arbitration
        on the next rebalance, so paper trading and search proceed concurrently.
        """
        active = deployment_context.get("active_deployments", [])
        root_goal = self._campaign.root_goal if self._campaign else goal

        paper_step = PlanStep(
            id=0,
            agent="executor",
            task={
                "task": "run_deployments",
                "campaign_id": self._campaign.id if self._campaign else "",
                "deployments": active,
            },
            description="Run active paper deployments",
            depends_on=[],
            status=StepStatus.APPROVED,
        )

        if not self._should_run_shadow_search():
            return Plan(
                id=str(uuid.uuid4())[:8],
                description=f"Run paper deployment portfolio for: {root_goal}",
                steps=[
                    paper_step,
                    PlanStep(
                        id=1,
                        agent="reporter",
                        task={"task": "summarize"},
                        description="Summarize paper deployment results",
                        depends_on=[0],
                        status=StepStatus.APPROVED,
                    ),
                ],
            )

        # Shadow search: build the discovery pipeline from the canonical
        # workflow template, renumber it to follow the paper executor step,
        # and let a single reporter summarize both branches.
        from quantclaw.orchestration.workflows import (
            WORKFLOW_TEMPLATES,
            plan_from_template,
        )
        template_plan = plan_from_template(
            WORKFLOW_TEMPLATES["factor_discovery"], root_goal
        )

        discovery_steps: list[PlanStep] = []
        last_search_id: int | None = None
        for step in template_plan.steps:
            if step.agent == "reporter":
                # Drop the template's reporter — we'll add a single combined one.
                continue
            new_id = step.id + 1
            new_deps = [d + 1 for d in step.depends_on]
            new_task = {**step.task, "shadow": True, "campaign_id":
                        self._campaign.id if self._campaign else ""}
            discovery_steps.append(PlanStep(
                id=new_id,
                agent=step.agent,
                task=new_task,
                description=f"Shadow search · {step.description}",
                depends_on=new_deps,
                status=StepStatus.APPROVED,
            ))
            last_search_id = new_id

        reporter_id = (last_search_id or 0) + 1
        reporter_deps = [0]
        if last_search_id is not None:
            reporter_deps.append(last_search_id)
        combined_reporter = PlanStep(
            id=reporter_id,
            agent="reporter",
            task={"task": "summarize", "shadow_search": True, "goal": root_goal},
            description="Summarize paper run + shadow search candidates",
            depends_on=reporter_deps,
            status=StepStatus.APPROVED,
        )

        return Plan(
            id=str(uuid.uuid4())[:8],
            description=f"Paper + shadow search for: {root_goal}",
            steps=[paper_step, *discovery_steps, combined_reporter],
        )

    def _should_run_shadow_search(self) -> bool:
        """True when this paper cycle should also run a discovery shadow search.

        Triggers every Nth paper cycle (1-indexed), where N comes from
        ``campaigns.paper_shadow_search_every``. ``0`` disables the feature.
        """
        if not self._campaign or self._campaign.phase != CampaignPhase.PAPER:
            return False
        every = int(self._config.get("campaigns", {}).get("paper_shadow_search_every", 3))
        if every <= 0:
            return False
        # phase_cycles is the count BEFORE this cycle's record_cycle increments it,
        # so the cycle being planned is phase_cycles + 1.
        cycle_being_planned = self._campaign.phase_cycles + 1
        return cycle_being_planned >= every and cycle_being_planned % every == 0

    async def _log_divergence(self, evaluation: dict, held_out: dict) -> None:
        """Log when the OODA evaluator's judgment diverged from held-out reality."""
        divergence = {
            "in_sample_sharpe": evaluation.get("best_result", {}).get("sharpe", 0),
            "held_out_sharpe": held_out.get("held_out_sharpe", 0),
            "held_out_verdict": held_out.get("verdict", ""),
            "degradation_ratio": held_out.get("degradation_ratio", 0),
            "test_accuracy": evaluation.get("best_result", {}).get("metrics", {}).get("test_accuracy", 0),
            "overfit_ratio": evaluation.get("best_result", {}).get("metrics", {}).get("overfit_ratio", 0),
            "model_type": evaluation.get("best_result", {}).get("model_type", ""),
            "ooda_verdict": evaluation.get("verdict", ""),
        }

        import logging
        logging.getLogger(__name__).warning(
            "Evaluator divergence: OODA said '%s' but held-out said '%s' (sharpe %.2f -> %.2f)",
            divergence["ooda_verdict"], divergence["held_out_verdict"],
            divergence["in_sample_sharpe"], divergence["held_out_sharpe"],
        )

        await self._playbook.add(
            EntryType.EVALUATOR_DIVERGENCE, divergence,
            tags=["auto", "calibration"],
        )

    async def _run_calibration(self) -> None:
        """Review divergence log and generate calibration rules for the evaluator."""
        divergences = await self._playbook.query(entry_type=EntryType.EVALUATOR_DIVERGENCE)
        if len(divergences) < 2:
            return  # Not enough data to calibrate

        # Analyze patterns in divergences
        rules = []

        # Check: are low-accuracy strategies consistently failing out-of-sample?
        low_acc_divergences = [
            d for d in divergences
            if d.content.get("test_accuracy", 1) < 0.55
        ]
        if len(low_acc_divergences) >= 2:
            rules.append(
                f"CALIBRATION: {len(low_acc_divergences)} of {len(divergences)} divergences had "
                f"test_accuracy < 55%. Strategies with test_accuracy below 55% are very likely overfit. "
                f"Weight accuracy heavily in your judgment."
            )

        # Check: are high overfit_ratio strategies failing?
        high_overfit = [
            d for d in divergences
            if d.content.get("overfit_ratio", 0) > 1.5
        ]
        if len(high_overfit) >= 2:
            rules.append(
                f"CALIBRATION: {len(high_overfit)} of {len(divergences)} divergences had "
                f"overfit_ratio > 1.5. Be skeptical of strategies with overfit_ratio above 1.5."
            )

        # Check: is degradation consistently below a threshold?
        avg_degradation = sum(
            d.content.get("degradation_ratio", 0) for d in divergences
        ) / len(divergences)
        if avg_degradation < 0.3:
            rules.append(
                f"CALIBRATION: Average degradation ratio across divergences is {avg_degradation:.1%}. "
                f"In-sample metrics are highly unreliable for this system. "
                f"Discount reported Sharpe by at least 70%."
            )

        if not rules:
            return

        # Save calibration rules (keep only max_rules most recent)
        eval_cfg = self._config.get("evaluator", {})
        max_rules = eval_cfg.get("max_calibration_rules", 10)

        existing = await self._playbook.query(entry_type=EntryType.EVALUATOR_CALIBRATION)
        existing_rules = [e.content.get("rule", "") for e in existing]

        for rule in rules:
            if rule not in existing_rules:
                await self._playbook.add(
                    EntryType.EVALUATOR_CALIBRATION,
                    {"rule": rule, "based_on_divergences": len(divergences)},
                    tags=["auto", "calibration"],
                )

        import logging
        logging.getLogger(__name__).info("Evaluator calibration: added %d rules", len(rules))

    async def run_continuous(self) -> None:
        """Run OODA loop continuously as a background task.

        Only runs cycles for autopilot mode with standing goals.
        Chat-triggered cycles are handled by the chat endpoint directly.
        """
        timeout_minutes = self._config.get("orchestration", {}).get("cycle_timeout_minutes", 20)
        interval = self._config.get("orchestration", {}).get("ooda_interval", 30)
        max_cycles = self._config.get("orchestration", {}).get("max_cycles_per_goal", 3)

        while True:
            await self.sleep_until_trigger(timeout=interval)
            self._wake_event.clear()  # Clear BEFORE checking lock to avoid race

            # Skip if a cycle is already running (triggered by chat endpoint)
            if self._cycle_lock.locked():
                continue

            # Only auto-cycle in autopilot mode with a standing goal
            if self._autonomy.mode != AutonomyMode.AUTOPILOT or not self._goal:
                continue
            if self._campaign and self._campaign.status.value != "active":
                continue

            try:
                await asyncio.wait_for(
                    self.run_cycle(),
                    timeout=timeout_minutes * 60,
                )
            except asyncio.TimeoutError:
                await self._bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={"message": f"Cycle timed out after {timeout_minutes} minutes.",
                             "role": "scheduler"},
                    source_agent="scheduler",
                ))

            # Broad campaigns keep running and checkpoint instead of hard stopping.
            if self._campaign:
                continue

            # Check cycle limit for non-campaign autopilot goals
            if (self._autonomy.mode == AutonomyMode.AUTOPILOT
                    and self._goal
                    and self._cycle_count >= max_cycles):
                await self._bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={
                        "message": f"Completed {max_cycles} cycles. Here's what I've found so far. Want me to keep exploring?",
                        "role": "scheduler",
                    },
                    source_agent="scheduler",
                ))
                self._cycle_count = 0

    def reset_campaign_state(self) -> None:
        """Clear all in-memory campaign + iteration state.

        Called by the `/api/reset` endpoint when the user wants a fresh start.
        Durable artifacts (playbook, state DB, generated strategies/models)
        are wiped by the endpoint itself; this method covers the in-memory
        counterpart so subsequent cycles don't resume the old campaign.
        """
        self._campaign = None
        self._goal = ""
        self._iteration_context = []
        self._cycle_count = 0
        self._pending_tasks = []
        self._current_contract = {}
        self._wake_event.clear()

    async def sleep(self) -> None:
        """SLEEP: Reset phase. For simple usage / tests."""
        self._phase = OODAPhase.SLEEP

    async def sleep_until_trigger(self, timeout: float = 30.0) -> None:
        """SLEEP: Wait for next trigger -- event-driven, not just timer.

        Wakes on market events, CEO instructions, agent completions,
        or timeout (whichever comes first).
        """
        self._phase = OODAPhase.SLEEP
        self._wake_event.clear()

        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass  # Timer trigger

        self._phase = OODAPhase.OBSERVE
