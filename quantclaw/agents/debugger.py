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
