"""Planner: decomposes natural language requests into executable plans."""
from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from quantclaw.execution.router import LLMRouter
from quantclaw.execution.plan import Plan, PlanStep, PlanStatus, StepStatus


@dataclass
class PlannedTask:
    agent: str
    task: dict
    depends_on: list[str] = field(default_factory=list)


class Planner:
    def __init__(self, router: LLMRouter):
        self._router = router
        self._plans: dict[str, Plan] = {}

    async def create_plan(self, request: str, context: dict | None = None) -> Plan:
        """Decompose a request into a Plan with steps."""
        playbook_section = ""
        iteration_section = ""
        exploration_section = ""
        campaign_section = ""
        deployment_section = ""

        if context:
            if context.get("playbook_context"):
                entries = context["playbook_context"][:5]
                playbook_section = "\n\nPlaybook (recent knowledge):\n"
                for e in entries:
                    playbook_section += f"- [{e.get('type', '')}] {str(e.get('content', ''))[:200]}\n"

            if context.get("campaign_context"):
                campaign = context["campaign_context"]
                campaign_section = (
                    "\n\nCampaign context:\n"
                    f"- Root goal: {campaign.get('root_goal', '')}\n"
                    f"- Phase: {campaign.get('phase', '')}\n"
                    f"- Total cycles: {campaign.get('total_cycles', 0)}\n"
                    f"- Best Sharpe so far: {campaign.get('best_sharpe', 0):.2f}\n"
                    f"- Best held-out Sharpe so far: {campaign.get('best_held_out_sharpe', 0):.2f}\n"
                    f"- Validated candidates: {campaign.get('validated_candidates', 0)}\n"
                    f"- Paper deployments: {campaign.get('paper_deployments', 0)}\n"
                    f"- Paper only: {campaign.get('paper_only', True)}\n"
                )

            if context.get("deployment_context"):
                deployments = context["deployment_context"]
                deployment_section = (
                    "\n\nDeployment allocator context:\n"
                    f"- Active slots: {deployments.get('active_slots', 0)}\n"
                    f"- Active deployments: {deployments.get('active_count', 0)}\n"
                    f"- Watchlist candidates: {deployments.get('watchlist_count', 0)}\n"
                    f"- Active set: {json.dumps(deployments.get('active_deployments', []))[:500]}\n"
                )

            if context.get("iteration_context"):
                iteration_section = "\n\nPrior iterations (DO NOT repeat these approaches):\n"
                for ic in context["iteration_context"]:
                    iteration_section += f"- Iteration {ic['iteration']}: best Sharpe {ic.get('best_sharpe', 0):.2f}\n"
                    if ic.get("avoid_factors"):
                        iteration_section += f"  Avoid factors: {', '.join(ic['avoid_factors'])}\n"
                    if ic.get("avoid_models"):
                        iteration_section += f"  Avoid models: {', '.join(ic['avoid_models'])}\n"
                iteration_section += "\nTry a COMPLETELY DIFFERENT approach — different factor families, different model types, different hypotheses.\n"

            if context.get("exploration_mode"):
                mode = context["exploration_mode"]
                temp = context.get("exploration_temp", 0.5)
                exploration_section = (
                    f"\n\nExploration mode: {mode} (temperature {temp}). "
                    f"You may override to explore|exploit|balanced if needed. "
                    f"If exploring, try unconventional approaches. "
                    f"If exploiting, refine what's working.\n"
                )

        from quantclaw.agents.manifest import format_manifest_for_prompt, AGENT_MANIFEST

        # Build task schema reference from manifest
        task_schemas = []
        for name, spec in AGENT_MANIFEST.items():
            if spec.task_schema and name != "scheduler":
                schema_str = ", ".join(f'"{k}": {v}' for k, v in spec.task_schema.items())
                task_schemas.append(f"- {name}: {{{schema_str}}}")
        task_schema_section = "\n".join(task_schemas)

        system = (
            "You are the QuantClaw planner. You decompose trading goals into executable agent workflows.\n\n"
            f"{format_manifest_for_prompt()}\n\n"
            f"TASK SCHEMAS (what to put in each agent's task dict):\n{task_schema_section}\n\n"

            "DATA FLOW RULES:\n"
            "- Steps with depends_on=[] run in parallel.\n"
            "- A step's output is automatically passed to dependent steps via _upstream_results.\n"
            "- Miner NEEDS ingestor data → set depends_on to include the ingestor step.\n"
            "- Trainer NEEDS miner factors → set depends_on to include the miner step.\n"
            "- Backtester NEEDS trainer output → set depends_on to include the trainer step.\n"
            "- Reporter should depend on ALL prior steps to summarize everything.\n\n"

            "EXAMPLE PLAN for 'find me profitable strategies':\n"
            "[{\"agent\": \"researcher\", \"task\": {\"topic\": \"promising alpha factors\", \"task\": \"search_factors\"}, "
            "\"description\": \"Research promising approaches\", \"depends_on\": []},\n"
            " {\"agent\": \"ingestor\", \"task\": {\"symbols\": [\"AAPL\", \"MSFT\", \"GOOG\", \"AMZN\", \"META\"]}, "
            "\"description\": \"Fetch market data\", \"depends_on\": []},\n"
            " {\"agent\": \"miner\", \"task\": {\"goal\": \"discover alpha factors\", "
            "\"symbols\": [\"AAPL\", \"MSFT\", \"GOOG\", \"AMZN\", \"META\"], \"generations\": 3}, "
            "\"description\": \"Mine alpha factors\", \"depends_on\": [0, 1]},\n"
            " {\"agent\": \"trainer\", \"task\": {\"model_type\": \"gradient_boosting\", "
            "\"symbols\": [\"AAPL\", \"MSFT\", \"GOOG\", \"AMZN\", \"META\"], \"forward_period\": 5}, "
            "\"description\": \"Train prediction model\", \"depends_on\": [2]},\n"
            " {\"agent\": \"validator\", \"task\": {\"task\": \"validate\", \"symbols\": [\"AAPL\", \"MSFT\", \"GOOG\", \"AMZN\", \"META\"]}, "
            "\"description\": \"Backtest + held-out validation\", \"depends_on\": [3]},\n"
            " {\"agent\": \"reporter\", \"task\": {\"task\": \"summarize\"}, "
            "\"description\": \"Generate report\", \"depends_on\": [4]}]\n\n"

            "RULES:\n"
            "- Return a JSON array, each item has: agent, task (dict), description (str), depends_on (list[int]).\n"
            "- Each step has a sequential id starting from 0.\n"
            "- Always include ingestor step when data is needed.\n"
            "- For any strategy-search workflow, use validator with task='validate' — it runs the in-sample backtest AND the held-out validation in a single step.\n"
            "- Always end with reporter for user-facing results.\n"
            "- If the user did not specify dates, omit start/end so agents can maximize usable history dynamically.\n"
            "- If campaign phase is paper and there are active deployments, manage the paper portfolio: "
            "keep the best incumbents, add only stronger validated candidates, and do NOT suggest live trading.\n"
            "- You have creative latitude — try novel factor ideas, different model types, parallel experiments.\n"
            "- For broad goals like 'make money', 'find strategies', 'go': ALWAYS plan a full pipeline "
            "(researcher + ingestor -> miner -> trainer -> validator -> reporter). "
            "Never just debug or research.\n"
            "- If the Playbook shows past failures (what_failed), learn from them — try DIFFERENT approaches, "
            "don't debug the old ones. The Debugger is only for diagnosing a specific runtime error.\n"
            "- Return ONLY valid JSON, no markdown or explanation."
            f"{playbook_section}{campaign_section}{deployment_section}{iteration_section}{exploration_section}"
        )

        temp = context.get("exploration_temp") if context else None

        response = await self._router.call(
            "planner",
            messages=[{"role": "user", "content": request}],
            system=system,
            temperature=temp,
        )

        try:
            tasks_data = json.loads(response)
        except json.JSONDecodeError:
            tasks_data = [
                {
                    "agent": "researcher",
                    "task": {"query": request},
                    "description": request,
                    "depends_on": [],
                }
            ]

        steps = []
        for i, t in enumerate(tasks_data):
            steps.append(PlanStep(
                id=i,
                agent=t.get("agent", "researcher"),
                task=t.get("task", {}) if isinstance(t.get("task"), dict) else {"task": str(t.get("task", ""))},
                description=t.get("description", f"Step {i}"),
                depends_on=t.get("depends_on", []),
            ))

        plan = Plan(
            id=str(uuid.uuid4())[:8],
            description=request,
            steps=steps,
        )
        errors = plan.validate()
        if errors:
            import logging
            logging.getLogger(__name__).warning("Plan validation errors: %s", errors)
            # Break cycles by removing problematic deps
            if any("Circular" in e for e in errors):
                for step in plan.steps:
                    step.depends_on = [d for d in step.depends_on if d < step.id]
        # Generate sprint contract based on Playbook context
        contract = self._generate_contract(context)
        plan.contract = contract

        self._plans[plan.id] = plan
        return plan

    def _generate_contract(self, context: dict | None) -> dict:
        """Generate sprint contract with success criteria.

        Config sets hard floors. Playbook context tightens them.
        """
        from quantclaw.config.loader import load_config
        config = load_config()
        contract_cfg = config.get("contracts", {})

        # Start with config hard floors
        contract = {
            "min_sharpe": contract_cfg.get("min_sharpe", 0.0),
            "max_overfit_ratio": contract_cfg.get("max_overfit_ratio", 3.0),
            "min_sample_size": contract_cfg.get("min_sample_size", 200),
            "min_trades": contract_cfg.get("min_trades", 10),
            "min_held_out_sharpe": contract_cfg.get("min_held_out_sharpe", 0.0),
            "held_out_months": contract_cfg.get("held_out_months", 3),
        }

        # Tighten based on Playbook context
        if context and context.get("playbook_context"):
            past_sharpes = []
            for entry in context["playbook_context"]:
                if isinstance(entry, dict):
                    content = entry.get("content", entry)
                    sharpe = content.get("sharpe", 0)
                    if sharpe and isinstance(sharpe, (int, float)) and sharpe > 0:
                        past_sharpes.append(sharpe)

            if len(past_sharpes) >= 3:
                import statistics
                median = statistics.median(past_sharpes)
                # Target above median of past results
                contract["min_sharpe"] = max(contract["min_sharpe"], median * 0.5)
                contract["min_held_out_sharpe"] = max(
                    contract["min_held_out_sharpe"], median * 0.25
                )

        return contract

    async def decompose(self, request: str) -> list[PlannedTask]:
        """Legacy method for backward compatibility."""
        plan = await self.create_plan(request)
        plan.approve_all()
        return [
            PlannedTask(agent=s.agent, task=s.task, depends_on=[])
            for s in plan.steps
        ]

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def list_plans(self) -> list[Plan]:
        return list(self._plans.values())
