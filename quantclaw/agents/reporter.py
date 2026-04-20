"""Reporter: generates structured reports from agent results.

Hybrid approach: template-based formatting for numbers/tables (no LLM),
plus a one-paragraph LLM-generated executive summary.
"""
from __future__ import annotations

import json
import logging

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ReporterAgent(BaseAgent):
    name = "reporter"
    model = "sonnet"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        task_type = task.get("task", "summarize")
        upstream = task.get("_upstream_results", {})

        # Collect all upstream data
        all_data: dict = {}
        for _step_id, data in upstream.items():
            if isinstance(data, dict):
                all_data.update(data)

        # Build structured report (template, no LLM)
        report = self._format_report(all_data, task_type)

        # Add LLM executive summary
        summary = await self._generate_summary(report, all_data)
        if summary:
            report = f"{summary}\n\n{report}"

        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "report": report,
                "summary": summary or "",
                "data": all_data,
            },
        )

    def _format_report(self, data: dict, task_type: str) -> str:
        """Template-based report formatting. No LLM call."""
        sections: list[str] = []

        # Performance section
        if "sharpe" in data or "annual_return" in data:
            perf: list[str] = []
            perf.append("Performance:")
            if "sharpe" in data:
                perf.append(f"  Sharpe Ratio:    {data['sharpe']:.2f}")
            if "annual_return" in data:
                perf.append(f"  Annual Return:   {data['annual_return']:.1%}")
            if "max_drawdown" in data:
                perf.append(f"  Max Drawdown:   {data['max_drawdown']:.1%}")
            if "win_rate" in data:
                perf.append(f"  Win Rate:        {data['win_rate']:.1%}")
            if "total_trades" in data:
                perf.append(f"  Total Trades:    {data['total_trades']}")
            sections.append("\n".join(perf))

        # Model section
        if "model_type" in data:
            model: list[str] = []
            model.append("Model:")
            model.append(f"  Type:            {data['model_type']}")
            if "features_used" in data:
                model.append(
                    f"  Features:        {', '.join(data['features_used'])}"
                )
            if "metrics" in data and isinstance(data["metrics"], dict):
                metrics = data["metrics"]
                if "overfit_ratio" in metrics:
                    ratio = metrics["overfit_ratio"]
                    if ratio < 1.5:
                        risk = "low"
                    elif ratio < 2.5:
                        risk = "moderate"
                    else:
                        risk = "high"
                    model.append(
                        f"  Overfit Ratio:   {ratio:.2f} ({risk})"
                    )
                if "test_accuracy" in metrics:
                    model.append(
                        f"  Test Accuracy:   {metrics['test_accuracy']:.1%}"
                    )
            sections.append("\n".join(model))

        # Factors section
        if "factors" in data and isinstance(data["factors"], list):
            factors: list[str] = []
            factors.append(f"Factors ({len(data['factors'])} discovered):")
            for f in data["factors"][:5]:
                name = f.get("name", "unnamed")
                sharpe = f.get("metrics", {}).get("sharpe", 0)
                ic = f.get("metrics", {}).get("ic", 0)
                factors.append(
                    f"  {name:20s}  Sharpe: {sharpe:.2f}  IC: {ic:.4f}"
                )
            sections.append("\n".join(factors))

        # Compliance section
        if "compliant" in data:
            risk: list[str] = []
            risk.append("Compliance:")
            risk.append(
                f"  Status:          {'PASS' if data['compliant'] else 'FAIL'}"
            )
            if "violations" in data:
                for v in data["violations"]:
                    risk.append(
                        f"  [{v.get('severity', '?')}] "
                        f"{v.get('rule', '')}: {v.get('detail', '')}"
                    )
            sections.append("\n".join(risk))

        # Research section
        if "findings" in data and isinstance(data["findings"], list):
            research: list[str] = []
            research.append(f"Research ({len(data['findings'])} findings):")
            for f in data["findings"][:3]:
                research.append(
                    f"  [{f.get('relevance', '?')}] {f.get('topic', '')}"
                )
                if f.get("recommendation"):
                    research.append(
                        f"         {f['recommendation'][:100]}"
                    )
            sections.append("\n".join(research))

        if not sections:
            return f"Report: {json.dumps(data, default=str)[:500]}"

        return "\n\n".join(sections)

    async def _generate_summary(self, report: str, data: dict) -> str:
        """Generate a one-paragraph executive summary via LLM."""
        try:
            from quantclaw.execution.router import LLMRouter

            router = LLMRouter(self._config)

            prompt = (
                "Write a 2-3 sentence executive summary of this trading "
                f"report. Be concise and actionable.\n\n{report[:2000]}"
            )

            response = await router.call(
                self.name,
                messages=[{"role": "user", "content": prompt}],
                system=(
                    "You are a concise financial report writer. "
                    "Summarize in 2-3 sentences. Be actionable — state what "
                    "worked, what didn't, and what the next step should be.\n\n"
                    f"{self.manifest_for_prompt()}"
                ),
            )
            return response.strip()
        except Exception:
            logger.exception("LLM summary generation failed")
            return ""
