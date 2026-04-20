"""Routes detected anomalies to appropriate diagnostic agents."""
from __future__ import annotations

import logging
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.plan import Plan, PlanStep
from quantclaw.agents.base import AgentResult, AgentStatus
from quantclaw.orchestration.diagnostics import AnomalyFlag

logger = logging.getLogger(__name__)


class DiagnosticRouter:
    """Invokes diagnostic agents based on detected anomalies."""

    def __init__(self, dispatcher: Dispatcher):
        self._dispatcher = dispatcher

    async def route_anomaly(
        self,
        anomaly: AnomalyFlag,
        evaluation_context: dict,
    ) -> AgentResult:
        """Dispatch anomaly to appropriate diagnostic agent.

        Args:
            anomaly: Detected anomaly with name and context
            evaluation_context: Full evaluation state including summary, campaign, etc.

        Returns:
            AgentResult with findings from diagnostic investigation
        """
        logger.info(f"Routing anomaly: {anomaly.name} (severity={anomaly.severity})")

        # Route by anomaly name
        route_map = {
            "held_out_outperforms_insample": self._audit_validation_pipeline,
            "metric_degradation": self._investigate_model_drift,
            "weak_held_out_signal": self._analyze_signal_weakness,
            "excessive_overfitting": self._diagnose_overfitting,
            "zero_orders_with_allocations": self._debug_executor,
            "all_deployments_failed": self._audit_deployment_loading,
            "stalled_watchlist_promotion": self._analyze_promotion_barriers,
            "portfolio_stagnation": self._research_new_allocation_opportunities,
            "sharpe_plateau": self._research_new_signals,
        }

        handler = route_map.get(anomaly.name)
        if not handler:
            logger.warning(f"No diagnostic handler for {anomaly.name}")
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"error": f"No handler for {anomaly.name}"}
            )

        try:
            result = await handler(anomaly, evaluation_context)
            return result
        except Exception as e:
            logger.exception(f"Diagnostic handler failed for {anomaly.name}")
            return AgentResult(
                status=AgentStatus.FAILED,
                data={"error": str(e)}
            )

    async def _audit_validation_pipeline(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Debugger to audit validation data pipeline."""
        plan = Plan(steps=[
            PlanStep(
                agent="debugger",
                task="audit_validation_data_pipeline",
                context={
                    "anomaly": anomaly.name,
                    "test_sharpe": context.get("test_sharpe"),
                    "held_out_sharpe": context.get("held_out_sharpe"),
                    "ratio": anomaly.context.get("ratio"),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _investigate_model_drift(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Researcher to investigate model performance degradation."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="investigate_model_drift",
                context={
                    "anomaly": anomaly.name,
                    "prior_sharpe": anomaly.context.get("prior_sharpe"),
                    "current_sharpe": anomaly.context.get("current_sharpe"),
                    "degradation_pct": anomaly.context.get("degradation_pct"),
                    "campaign_metrics": context.get("campaign", {}),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _analyze_signal_weakness(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Researcher to analyze weak signal and suggest improvements."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="analyze_weak_signal",
                context={
                    "anomaly": anomaly.name,
                    "held_out_sharpe": anomaly.context.get("held_out_sharpe"),
                    "current_factors": context.get("current_factors", []),
                    "market_regime": context.get("market_regime"),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _diagnose_overfitting(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Debugger to diagnose overfitting and suggest fixes."""
        plan = Plan(steps=[
            PlanStep(
                agent="debugger",
                task="diagnose_overfitting",
                context={
                    "anomaly": anomaly.name,
                    "overfit_ratio": anomaly.context.get("overfit_ratio"),
                    "test_sharpe": context.get("test_sharpe"),
                    "held_out_sharpe": context.get("held_out_sharpe"),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _debug_executor(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Debugger to audit deployment executor logic."""
        plan = Plan(steps=[
            PlanStep(
                agent="debugger",
                task="audit_paper_deployment_executor",
                context={
                    "anomaly": anomaly.name,
                    "active_deployments": anomaly.context.get("successful_deployments"),
                    "orders_executed": anomaly.context.get("orders_executed"),
                    "portfolio_state": context.get("portfolio_state", {}),
                    "cash_available": context.get("cash_available"),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _audit_deployment_loading(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Debugger to audit deployment/model loading."""
        plan = Plan(steps=[
            PlanStep(
                agent="debugger",
                task="audit_deployment_model_loading",
                context={
                    "anomaly": anomaly.name,
                    "failed_count": anomaly.context.get("failed_deployments"),
                    "active_deployments": context.get("active_deployments", []),
                    "error_logs": context.get("deployment_errors", []),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _analyze_promotion_barriers(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Researcher to analyze why candidates don't promote."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="analyze_candidate_promotion_barriers",
                context={
                    "anomaly": anomaly.name,
                    "watchlist_size": anomaly.context.get("watchlist_size"),
                    "cycles_stalled": anomaly.context.get("cycles_stalled"),
                    "candidate_sharpe": anomaly.context.get("candidate_sharpe"),
                    "incumbent_sharpe": anomaly.context.get("incumbent_sharpe"),
                    "compliance_rules": context.get("compliance_rules", {}),
                    "promotion_gates": context.get("promotion_gates", {}),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _research_new_allocation_opportunities(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Researcher to find new allocation opportunities."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="find_new_allocation_opportunities",
                context={
                    "anomaly": anomaly.name,
                    "cycles_stalled": anomaly.context.get("cycles_without_change"),
                    "current_allocation": context.get("current_allocation", {}),
                    "market_data": context.get("market_data", {}),
                },
            )
        ])
        return await self._dispatcher.execute(plan)

    async def _research_new_signals(
        self,
        anomaly: AnomalyFlag,
        context: dict,
    ) -> AgentResult:
        """Invoke Researcher to discover new trading signals."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="discover_new_trading_signals",
                context={
                    "anomaly": anomaly.name,
                    "sharpe_plateau": anomaly.context.get("recent_best"),
                    "stalled_cycles": anomaly.context.get("stalled_cycles"),
                    "current_factors": context.get("current_factors", []),
                    "market_regime": context.get("market_regime"),
                },
            )
        ])
        return await self._dispatcher.execute(plan)
