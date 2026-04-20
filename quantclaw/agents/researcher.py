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
        topic = task.get("topic", task.get("query", task.get("task", "")))
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
