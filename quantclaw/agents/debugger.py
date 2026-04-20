"""Debugger: pipeline failure analysis and recovery suggestions."""
from __future__ import annotations

import json
import logging

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class DebuggerAgent(BaseAgent):
    name = "debugger"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        task_name = task.get("task", "")

        # Route diagnostic tasks
        if task_name == "audit_validation_data_pipeline":
            return await self._audit_validation_data_pipeline(task.get("context", {}))
        elif task_name == "audit_paper_deployment_executor":
            return await self._audit_paper_deployment_executor(task.get("context", {}))
        elif task_name == "audit_deployment_model_loading":
            return await self._audit_deployment_model_loading(task.get("context", {}))
        elif task_name == "diagnose_overfitting":
            return await self._diagnose_overfitting(task.get("context", {}))

        # Legacy error diagnosis
        error = task.get("error", "")
        context = task.get("context", "")
        agent_name = task.get("agent", "")
        stack_trace = task.get("stack_trace", "")

        if not error:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="No error provided to diagnose",
            )

        try:
            diagnosis = await self._diagnose(error, context, agent_name, stack_trace)
            return AgentResult(status=AgentStatus.SUCCESS, data=diagnosis)
        except Exception:
            logger.exception("Debugger diagnosis failed")
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={
                    "diagnosis": "Unable to analyze error via LLM",
                    "error_type": "unknown",
                    "suggestions": [f"Manual review needed: {error[:200]}"],
                    "recoverable": False,
                },
            )

    async def _diagnose(self, error: str, context: str, agent_name: str, stack_trace: str) -> dict:
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Diagnose this pipeline error:\n\n"
            f"Agent: {agent_name}\n"
            f"Error: {error}\n"
            f"Stack trace: {stack_trace[:1000]}\n"
            f"Context: {context[:500]}\n\n"
            f"Return JSON with:\n"
            f'- "diagnosis": string explaining the root cause\n'
            f'- "error_type": one of "data", "model", "config", "network", "resource", "code"\n'
            f'- "suggestions": list of actionable fix suggestions\n'
            f'- "recoverable": boolean - can this be retried with changes?\n'
            f'- "retry_with": dict of task modifications to fix it (or empty dict)\n'
            f"Return ONLY valid JSON."
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a debugging expert for quantitative trading pipelines. "
                "Analyze errors and suggest fixes.\n\n"
                f"{self.manifest_for_prompt()}\n\n"
                "Use your knowledge of the agent system to pinpoint root causes. "
                "If the error is in data flow between agents, suggest which "
                "upstream agent needs different parameters."
            ),
            temperature=0.3,
        )

        result = json.loads(response)
        if isinstance(result, dict) and "diagnosis" in result:
            return result

        return {
            "diagnosis": response[:500],
            "error_type": "unknown",
            "suggestions": [],
            "recoverable": False,
            "retry_with": {},
        }

    async def _audit_validation_data_pipeline(self, context: dict) -> AgentResult:
        """Audit validation data pipeline for leakage or misalignment."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Audit this validation pipeline issue:\n\n"
            f"Anomaly: {context.get('anomaly', 'unknown')}\n"
            f"Test Sharpe: {context.get('test_sharpe', 0):.2f}\n"
            f"Held-out Sharpe: {context.get('held_out_sharpe', 0):.2f}\n"
            f"Ratio: {context.get('ratio', 0):.2f}\n\n"
            f"Questions to investigate:\n"
            f"1. Is there data leakage between train/test/held-out splits?\n"
            f"2. Are timestamps aligned correctly (no look-ahead bias)?\n"
            f"3. Are feature calculations using the same data availability as backtest?\n"
            f"4. Could the discrepancy be normal variance or systematic bias?\n\n"
            f"Return JSON with:\n"
            f'- "root_cause": string explaining the likely issue\n'
            f'- "severity": "critical", "high", or "medium"\n'
            f'- "summary": short actionable insight\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are an expert in backtesting methodology and data pipeline validation. "
                "Identify data quality issues, leakage, and methodological problems."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "root_cause": "Validation data issue detected",
                "severity": "high",
                "summary": response[:200]
            })

    async def _audit_paper_deployment_executor(self, context: dict) -> AgentResult:
        """Audit paper deployment executor for logic issues."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Diagnose paper trading execution issue:\n\n"
            f"Active deployments: {context.get('active_deployments', 0)}\n"
            f"Orders executed: {context.get('orders_executed', 0)}\n"
            f"Portfolio state: {json.dumps(context.get('portfolio_state', {}), indent=2)[:500]}\n"
            f"Cash available: {context.get('cash_available', 0)}\n\n"
            f"The executor has allocations but generated zero orders. Why?\n"
            f"Likely causes:\n"
            f"- All-in allocation leaving no cash for rebalancing\n"
            f"- Target weights already match current weights\n"
            f"- Minimum order size threshold filtering out small adjustments\n"
            f"- Signal generation failure\n\n"
            f"Return JSON with:\n"
            f'- "root_cause": specific issue preventing orders\n'
            f'- "recommended_fix": concrete action to take\n'
            f'- "summary": brief explanation\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are an expert in portfolio execution logic. "
                "Analyze why a live executor might produce zero orders despite active allocations."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "root_cause": "Executor logic issue",
                "recommended_fix": "Verify cash availability and minimum order constraints",
                "summary": response[:200]
            })

    async def _audit_deployment_model_loading(self, context: dict) -> AgentResult:
        """Audit model loading and deployment failures."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Diagnose deployment model loading failures:\n\n"
            f"Failed deployments: {context.get('failed_count', 0)}\n"
            f"Active deployments: {context.get('active_deployments', [])}\n"
            f"Error logs:\n"
            f"{chr(10).join(context.get('error_logs', ['No logs available'])[:5])}\n\n"
            f"Why are all deployments failing?\n"
            f"Common causes:\n"
            f"- Model file missing or corrupted\n"
            f"- Feature names don't match model expectations\n"
            f"- Pickle version mismatch\n"
            f"- Required libraries not installed\n\n"
            f"Return JSON with:\n"
            f'- "root_cause": category of failure\n'
            f'- "suggested_action": specific fix\n'
            f'- "summary": brief diagnosis\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are an expert in ML model deployment and artifact management. "
                "Diagnose why models fail to load in production."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "root_cause": "Model loading failure",
                "suggested_action": "Check model artifacts and feature alignment",
                "summary": response[:200]
            })

    async def _diagnose_overfitting(self, context: dict) -> AgentResult:
        """Diagnose overfitting and suggest parameter adjustments."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Analyze overfitting in this strategy:\n\n"
            f"Overfit ratio: {context.get('overfit_ratio', 1.0):.2f}\n"
            f"Test Sharpe: {context.get('test_sharpe', 0):.2f}\n"
            f"Held-out Sharpe: {context.get('held_out_sharpe', 0):.2f}\n"
            f"Anomaly: {context.get('anomaly', 'excessive_overfitting')}\n\n"
            f"The strategy shows signs of overfitting (test >> held-out performance).\n"
            f"Suggest specific fixes:\n"
            f"- Reduce model complexity (fewer features, simpler model)\n"
            f"- Increase regularization\n"
            f"- Use walk-forward validation\n"
            f"- Expand dataset\n\n"
            f"Return JSON with:\n"
            f'- "diagnosis": why overfitting occurred\n'
            f'- "suggested_fixes": list of specific parameter changes\n'
            f'- "summary": quick fix to try first\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are an expert in machine learning model validation and overfitting diagnosis. "
                "Suggest concrete fixes for overfit models."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "diagnosis": "Model overfitting detected",
                "suggested_fixes": ["Reduce features", "Increase regularization", "Expand data"],
                "summary": response[:200]
            })
