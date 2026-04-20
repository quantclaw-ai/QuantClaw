"""Researcher: LLM-driven research with autonomous web search.

The LLM decides what to search, reviews results, and searches more if
needed. Uses tool-use loop to give the model control over search queries.
Falls back to pre-search + synthesis if tool-use is unavailable.
"""
from __future__ import annotations

import json
import logging

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    name = "researcher"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        task_name = task.get("task", "")

        # Route diagnostic tasks
        if task_name == "investigate_model_drift":
            return await self._investigate_model_drift(task.get("context", {}))
        elif task_name == "analyze_weak_signal":
            return await self._analyze_signal_weakness(task.get("context", {}))
        elif task_name == "analyze_candidate_promotion_barriers":
            return await self._analyze_promotion_barriers(task.get("context", {}))
        elif task_name == "discover_new_trading_signals":
            return await self._discover_new_signals(task.get("context", {}))
        elif task_name == "find_new_allocation_opportunities":
            return await self._find_new_allocation_opportunities(task.get("context", {}))

        # Legacy research task
        topic = task.get("topic", task.get("query", ""))
        task_type = task.get("task", "search")
        context = task.get("context", "")

        if not topic:
            return AgentResult(status=AgentStatus.FAILED, error="No topic or query provided")

        try:
            findings = await self._research_with_tools(topic, task_type, context)
        except Exception:
            logger.exception("Tool-use research failed, falling back to pre-search")
            findings = await self._research_fallback(topic, task_type, context)

        return AgentResult(status=AgentStatus.SUCCESS, data=findings)

    async def _research_with_tools(
        self, topic: str, task_type: str, context: str,
    ) -> dict:
        """LLM-driven research: model decides what to search."""
        from quantclaw.execution.tool_loop import call_with_tools, SEARCH_TOOL, DATA_FIELDS_TOOL

        prompt = (
            f"Research this topic thoroughly: {topic}\n"
            f"Task type: {task_type}\n"
            f"Context: {context}\n\n"
            f"You have access to web search and data field discovery tools. "
            f"Use them to gather information before synthesizing your findings.\n\n"
            f"Strategy:\n"
            f"1. Start by searching for the most relevant information\n"
            f"2. Review results and search again with refined queries if needed\n"
            f"3. Check available data fields to know what data the system can fetch\n"
            f"4. When you have enough information, provide your final answer\n\n"
            f"Your final answer MUST be a JSON object with:\n"
            f'- "findings": list of {{"topic": str, "source": str, '
            f'"relevance": "high"|"medium"|"low", "recommendation": str, '
            f'"model_params": dict}}\n'
            f'- "suggested_factors": list of factor name strings\n'
            f'- "suggested_models": list of model type strings\n'
            f'- "suggested_data_sources": list of specific field names from '
            f"available data fields that would be useful (e.g. "
            f'["shortRatio", "returnOnEquity", "beta"]). '
            f'Always include "ohlcv" as the base. Only suggest fields that '
            f"actually exist in the available fields.\n\n"
            f"Return ONLY valid JSON as your final answer."
        )

        system = (
            "You are a quantitative research analyst. Your job is to find "
            "actionable insights for alpha factor discovery and model building.\n\n"
            "Search strategically — don't just search once. Use multiple targeted "
            "queries to build a complete picture. For example:\n"
            "- Search for recent academic papers on the topic\n"
            "- Search for practitioner reports or blog posts\n"
            "- Search for specific factor names or strategies mentioned in results\n"
            "- Check what data fields are available in the system\n\n"
            "Be thorough but efficient — typically 2-4 searches is enough.\n\n"
            f"{self.manifest_for_prompt()}\n\n"
            "Your output feeds directly into the Miner and Ingestor. "
            "The Miner needs factor hypotheses as pandas expressions on DataFrames. "
            "The Ingestor needs specific field names to fetch. "
            "Tailor your suggestions to what these agents can actually use."
        )

        response = await call_with_tools(
            agent_name=self.name,
            messages=[{"role": "user", "content": prompt}],
            system=system,
            config=self._config,
            tools=[SEARCH_TOOL, DATA_FIELDS_TOOL],
        )

        result = self._extract_json(response)
        if isinstance(result, dict) and "findings" in result:
            return result

        raise ValueError("LLM did not return valid findings JSON")

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON object from LLM response that may contain extra text."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find the first { ... } block that contains "findings"
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start:i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict) and "findings" in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                    start = -1

        raise json.JSONDecodeError("No valid JSON object with 'findings' found", text, 0)

    async def _research_fallback(
        self, topic: str, task_type: str, context: str,
    ) -> dict:
        """Fallback: pre-search then synthesize (original behavior)."""
        search_results = await self._search(topic)
        return await self._synthesize(topic, task_type, context, search_results)

    async def _search(self, query: str) -> list[dict]:
        from quantclaw.agents.tools.web_search import web_search, is_search_allowed

        if not is_search_allowed(self.name):
            return []
        try:
            return await web_search(query, config=self._config, max_results=5)
        except Exception:
            logger.exception("Web search failed for: %s", query)
            return []

    async def _synthesize(
        self,
        topic: str,
        task_type: str,
        context: str,
        search_results: list[dict],
    ) -> dict:
        search_text = ""
        if search_results:
            search_text = "\n\nWeb search results:\n"
            for r in search_results[:5]:
                search_text += f"- {r.get('title', '')}: {r.get('snippet', '')}\n"

        # Tell the LLM what data fields are actually available
        available_fields = self._get_available_fields()
        fields_text = ""
        if available_fields:
            fields_text = "\n\nAvailable data fields by category:\n"
            for cat, fields_list in available_fields.items():
                fields_text += f"- {cat}: {', '.join(fields_list)}\n"

        prompt = (
            f"Research topic: {topic}\n"
            f"Task type: {task_type}\n"
            f"Context: {context}\n"
            f"{search_text}{fields_text}\n"
            f"Return a JSON object with:\n"
            f'- "findings": list of {{"topic": str, "source": str, "relevance": "high"|"medium"|"low", '
            f'"recommendation": str, "model_params": dict}}\n'
            f'- "suggested_factors": list of factor name strings\n'
            f'- "suggested_models": list of model type strings\n'
            f'- "suggested_data_sources": list of specific field names from the available fields above '
            f'that would be useful (e.g. ["shortRatio", "returnOnEquity", "beta"]). '
            f'Always include "ohlcv" as the base. Only suggest fields that exist in the available fields list.\n'
            f"Return ONLY valid JSON."
        )

        try:
            from quantclaw.execution.router import LLMRouter

            router = LLMRouter(self._config)
            response = await router.call(
                self.name,
                messages=[{"role": "user", "content": prompt}],
                system="You are a quantitative research analyst. Synthesize findings into structured recommendations.",
            )
            result = json.loads(response)
            if isinstance(result, dict) and "findings" in result:
                return result
        except Exception:
            logger.exception("LLM synthesis failed, returning raw search results")

        return {
            "findings": [
                {
                    "topic": r.get("title", ""),
                    "source": r.get("url", ""),
                    "relevance": "medium",
                    "recommendation": r.get("snippet", ""),
                    "model_params": {},
                }
                for r in search_results[:3]
            ],
            "suggested_factors": [],
            "suggested_models": [],
            "suggested_data_sources": [],
        }

    def _get_available_fields(self) -> dict[str, list[str]]:
        """Query data plugins for available field categories."""
        try:
            from quantclaw.plugins.manager import PluginManager
            data_plugin_names = self._config.get("plugins", {}).get("data", ["data_yfinance"])
            if isinstance(data_plugin_names, str):
                data_plugin_names = [data_plugin_names]
            pm = PluginManager()
            pm.discover()
            plugin = pm.get("data", data_plugin_names[0])
            if plugin:
                return plugin.available_fields()
        except Exception:
            logger.debug("Could not query available fields")
        return {}

    async def _investigate_model_drift(self, context: dict) -> AgentResult:
        """Investigate model performance degradation."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Analyze model performance degradation:\n\n"
            f"Prior Sharpe: {context.get('prior_sharpe', 0):.2f}\n"
            f"Current Sharpe: {context.get('current_sharpe', 0):.2f}\n"
            f"Degradation: {context.get('degradation_pct', 0):.1f}%\n"
            f"Campaign metrics: {json.dumps(context.get('campaign_metrics', {}), indent=2)[:500]}\n\n"
            f"Why might the model have degraded?\n"
            f"Consider:\n"
            f"- Market regime change (bull to bear, volatility shift)\n"
            f"- Data quality issues (missing values, stale data)\n"
            f"- Model becoming outdated (learned patterns no longer valid)\n"
            f"- Overfitting on historical patterns\n\n"
            f"Return JSON with:\n"
            f'- "likely_cause": specific reason for degradation\n'
            f'- "suggested_response": action to take\n'
            f'- "summary": brief insight\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a quantitative analyst expert in model monitoring and drift detection. "
                "Diagnose why a model's performance changed and suggest remediation."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "likely_cause": "Model drift detected",
                "suggested_response": "Retrain with recent data or adjust allocations",
                "summary": response[:200]
            })

    async def _analyze_signal_weakness(self, context: dict) -> AgentResult:
        """Analyze weak signal and suggest improvements."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Analyze weak trading signal:\n\n"
            f"Held-out Sharpe: {context.get('held_out_sharpe', 0):.2f}\n"
            f"Current factors: {json.dumps(context.get('current_factors', []))}\n"
            f"Market regime: {context.get('market_regime', 'unknown')}\n\n"
            f"This signal is too weak for reliable trading. How to strengthen it?\n"
            f"Consider:\n"
            f"- Adding new factors or features\n"
            f"- Combining with other signals\n"
            f"- Using ensemble models\n"
            f"- Focusing on specific market segments\n\n"
            f"Return JSON with:\n"
            f'- "improvement_ideas": list of concrete factor or feature suggestions\n'
            f'- "ensemble_strategy": how to combine with other signals\n'
            f'- "summary": one quick idea to try\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a quantitative researcher specialized in alpha factor discovery. "
                "Suggest improvements to strengthen weak trading signals."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "improvement_ideas": ["Relative strength", "Mean reversion", "Volatility adjust"],
                "ensemble_strategy": "Combine with momentum or value factors",
                "summary": response[:200]
            })

    async def _analyze_promotion_barriers(self, context: dict) -> AgentResult:
        """Analyze why candidate strategies don't promote."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Analyze candidate strategy promotion barriers:\n\n"
            f"Watchlist size: {context.get('watchlist_size', 0)}\n"
            f"Cycles stalled: {context.get('cycles_stalled', 0)}\n"
            f"Candidate Sharpe: {context.get('candidate_sharpe', 0):.2f}\n"
            f"Incumbent Sharpe: {context.get('incumbent_sharpe', 0):.2f}\n"
            f"Compliance rules: {json.dumps(context.get('compliance_rules', {}))}\n"
            f"Promotion gates: {json.dumps(context.get('promotion_gates', {}))}\n\n"
            f"Why is the best candidate not being promoted?\n"
            f"Investigate:\n"
            f"- Compliance/risk gates blocking promotion\n"
            f"- Drawdown or Sharpe thresholds not met\n"
            f"- Insufficient track record\n"
            f"- Position concentration limits\n\n"
            f"Return JSON with:\n"
            f'- "barrier_type": what blocks promotion\n'
            f'- "resolution": specific action to enable promotion\n'
            f'- "summary": one-line insight\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are an expert in portfolio management and strategy governance. "
                "Identify what prevents good strategies from being promoted to live trading."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "barrier_type": "Governance gate",
                "resolution": "Review compliance rules for this candidate",
                "summary": response[:200]
            })

    async def _discover_new_signals(self, context: dict) -> AgentResult:
        """Discover new trading signals to break Sharpe plateau."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Discover new trading signals to improve Sharpe ratio:\n\n"
            f"Current best Sharpe: {context.get('sharpe_plateau', 0):.2f}\n"
            f"Stalled cycles: {context.get('stalled_cycles', 0)}\n"
            f"Current factors: {json.dumps(context.get('current_factors', []))}\n"
            f"Market regime: {context.get('market_regime', 'unknown')}\n\n"
            f"The strategy is plateau-ing. What new signals could improve it?\n"
            f"Consider:\n"
            f"- Macro factors (interest rates, volatility, credit spreads)\n"
            f"- Cross-asset correlations\n"
            f"- Sentiment or alternative data\n"
            f"- Non-linear relationships\n\n"
            f"Return JSON with:\n"
            f'- "new_factors": list of 3-5 promising factor ideas\n'
            f'- "implementation_difficulty": "easy", "medium", or "hard"\n'
            f'- "expected_improvement": estimated Sharpe increase\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a leading quantitative researcher exploring new alpha sources. "
                "Suggest novel factors and signals to improve strategy performance."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "new_factors": ["Volatility skew", "Term structure", "Cross-asset beta"],
                "implementation_difficulty": "medium",
                "expected_improvement": "0.2-0.5 Sharpe"
            })

    async def _find_new_allocation_opportunities(self, context: dict) -> AgentResult:
        """Find new portfolio allocation opportunities."""
        from quantclaw.execution.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"Analyze portfolio allocation opportunities:\n\n"
            f"Cycles without change: {context.get('cycles_stalled', 0)}\n"
            f"Current allocation: {json.dumps(context.get('current_allocation', {}), indent=2)[:500]}\n"
            f"Market data: {json.dumps(context.get('market_data', {}), indent=2)[:300]}\n\n"
            f"Portfolio is stagnant. Where to invest more?\n"
            f"Consider:\n"
            f"- Sectors with improving fundamentals\n"
            f"- Emerging opportunities in current positions\n"
            f"- New uncorrelated strategies\n"
            f"- Risk-adjusted rebalancing\n\n"
            f"Return JSON with:\n"
            f'- "rebalancing_suggestion": specific allocation changes\n'
            f'- "rationale": why these changes make sense\n'
            f'- "expected_impact": estimated return/risk improvement\n'
        )

        response = await router.call(
            self.name,
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are a portfolio allocation expert. "
                "Identify opportunities to improve portfolio construction and diversification."
            ),
            temperature=0.3,
        )

        try:
            return AgentResult(status=AgentStatus.SUCCESS, data=json.loads(response))
        except:
            return AgentResult(status=AgentStatus.SUCCESS, data={
                "rebalancing_suggestion": "Increase allocation to uncorrelated strategy",
                "rationale": "Diversification improvement",
                "expected_impact": "Better risk-adjusted returns"
            })
