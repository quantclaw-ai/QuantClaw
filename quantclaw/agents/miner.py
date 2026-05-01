"""Miner: evolutionary alpha factor discovery.

Uses LLM for creative hypothesis generation, runs factor code in sandbox,
evaluates with IC/Rank IC/Sharpe metrics, and evolves factors through
mutation, crossover, and exploration.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

FALLBACK_FACTORS = [
    {"name": "momentum_5d", "hypothesis": "5-day price momentum",
     "code": "df['close'].pct_change(5)", "data_types": ["price"]},
    {"name": "momentum_20d", "hypothesis": "20-day price momentum",
     "code": "df['close'].pct_change(20)", "data_types": ["price"]},
    {"name": "volatility_20d", "hypothesis": "20-day rolling volatility",
     "code": "df['close'].pct_change().rolling(20).std()", "data_types": ["price"]},
    {"name": "mean_reversion_10d", "hypothesis": "10-day mean reversion (z-score)",
     "code": "(df['close'] - df['close'].rolling(10).mean()) / df['close'].rolling(10).std()",
     "data_types": ["price"]},
]


class MinerAgent(BaseAgent):
    name = "miner"
    model = "gpt"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        goal = task.get("goal", task.get("task", "discover factors"))
        symbols = task.get("symbols", [])
        generations = task.get("generations", 3)
        playbook_context = task.get("playbook_context", [])

        # Discover available columns from upstream Ingestor/Researcher
        available_columns = self._extract_available_columns(task)
        history_context = self._extract_history_context(task)

        factors = await self._generate_hypotheses(
            goal,
            playbook_context,
            available_columns,
            history_context=history_context,
        )

        if not factors:
            factors = list(FALLBACK_FACTORS)

        await self._narrate(
            f"Generation 1/{generations}: evaluating {len(factors)} candidate factor{'s' if len(factors) != 1 else ''}…"
        )

        if symbols:
            factors = await self._evaluate_factors(factors, symbols, task)

        # Evolutionary loop
        for gen in range(1, generations):
            if not factors:
                break
            # Rank by Sharpe, take top parents
            ranked = sorted(factors, key=lambda f: f.get("metrics", {}).get("sharpe", 0), reverse=True)
            parents = ranked[:3]
            best_so_far = ranked[0].get("metrics", {}).get("sharpe", 0) if ranked else 0
            await self._narrate(
                f"Generation {gen + 1}/{generations}: best Sharpe so far {best_so_far:.2f}, evolving {len(parents)} parents…"
            )

            # Evolve
            new_factors = await self._evolve_factors(
                parents,
                gen,
                symbols,
                task,
                available_columns,
                history_context=history_context,
            )
            if new_factors and symbols:
                new_factors = await self._evaluate_factors(new_factors, symbols, task)

            # Merge: keep best unique factors
            all_names = {f["name"] for f in factors}
            for nf in new_factors:
                if nf["name"] not in all_names:
                    factors.append(nf)
                    all_names.add(nf["name"])

            # Prune to best 6
            factors = sorted(factors, key=lambda f: f.get("metrics", {}).get("sharpe", 0), reverse=True)[:6]

        if not factors:
            return AgentResult(status=AgentStatus.FAILED, error="No factors generated")

        best_sharpe = max(
            (f.get("metrics", {}).get("sharpe", 0) for f in factors), default=0
        )
        best_ic = max(
            (f.get("metrics", {}).get("ic", 0) for f in factors), default=0
        )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "factors": factors,
                "generations_run": generations,
                "best_sharpe": best_sharpe,
                "best_ic": best_ic,
            },
        )

    def _extract_available_columns(self, task: dict) -> list[str]:
        """Extract available columns from upstream Ingestor results."""
        base = ["open", "high", "low", "close", "volume"]
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict) and "columns" in data:
                cols = data["columns"]
                if isinstance(cols, list):
                    return cols
        return base

    async def _generate_hypotheses(self, goal: str, playbook_context: list,
                                   available_columns: list[str] | None = None,
                                   history_context: str = "") -> list[dict]:
        columns = available_columns or ["open", "high", "low", "close", "volume"]
        columns_str = ", ".join(columns)

        try:
            from quantclaw.execution.router import LLMRouter
            router = LLMRouter(self._config)

            context_str = ""
            if playbook_context:
                context_str = "\n\nPast results:\n"
                for entry in playbook_context[:5]:
                    context_str += f"- {json.dumps(entry.get('content', {}))[:200]}\n"

            # Identify extra columns beyond OHLCV
            extra = [c for c in columns if c not in ("open", "high", "low", "close", "volume")]
            extra_hint = ""
            if extra:
                extra_hint = (
                    f"\n\nYou also have these additional columns: {', '.join(extra)}. "
                    f"Some may be shorter-history time series while others may be snapshots. "
                    f"Use them when they add real value, but be mindful that shorter-history "
                    f"fields reduce effective sample depth."
                )

            prompt = (
                f"Generate 3 alpha factor hypotheses for: {goal}\n"
                f"Each factor should be a pandas expression on a DataFrame 'df' with columns: "
                f"{columns_str}.\n"
                f"{history_context}\n"
                f"{extra_hint}{context_str}\n"
                f"Return JSON array: [{{\"name\": str, \"hypothesis\": str, \"code\": str, "
                f"\"data_types\": [str]}}]\n"
                f"Return ONLY valid JSON."
            )

            response = await router.call(
                self.name,
                messages=[{"role": "user", "content": prompt}],
                system=(
                    "You are a quantitative researcher. Generate creative alpha factor "
                    "hypotheses as executable pandas code.\n\n"
                    f"{self.manifest_for_prompt()}\n\n"
                    "Your factors feed directly into the Trainer, which builds ML models "
                    "from them. Each factor MUST be a single pandas expression that "
                    "produces a Series when applied to a DataFrame 'df'. The Trainer "
                    "will use these as features for classification (predict direction)."
                ),
            )

            factors = json.loads(response)
            if isinstance(factors, list):
                return factors
        except Exception:
            logger.exception("LLM hypothesis generation failed, using fallback")

        return []

    async def _evolve_factors(
        self, parents: list[dict], generation: int,
        symbols: list[str], task: dict,
        available_columns: list[str],
        history_context: str = "",
    ) -> list[dict]:
        """Generate mutated/crossover variants from parent factors."""
        columns_str = ", ".join(available_columns or ["open", "high", "low", "close", "volume"])

        parent_descriptions = []
        for p in parents[:3]:
            parent_descriptions.append(
                f"- {p['name']} (sharpe={p.get('metrics',{}).get('sharpe',0):.3f}): {p['code']}"
            )
        parents_text = "\n".join(parent_descriptions)

        prompt = (
            f"You are evolving alpha factors. Here are the best-performing parent factors:\n"
            f"{parents_text}\n\n"
            f"Generate 3 NEW factor variants by:\n"
            f"1. Mutating a parent (change a parameter, window size, or operator)\n"
            f"2. Crossing over two parents (combine elements from different parents)\n"
            f"3. Exploring a related but different hypothesis\n\n"
            f"Each factor should be a pandas expression on a DataFrame 'df' with columns: {columns_str}.\n"
            f"{history_context}\n"
            f"Return JSON array: [{{\"name\": str, \"hypothesis\": str, \"code\": str, \"data_types\": [str]}}]\n"
            f"Return ONLY valid JSON."
        )

        try:
            from quantclaw.execution.router import LLMRouter
            router = LLMRouter(self._config)
            response = await router.call(
                self.name,
                messages=[{"role": "user", "content": prompt}],
                system="You are a quantitative researcher evolving alpha factors through mutation and crossover.",
            )
            factors = json.loads(response)
            if isinstance(factors, list):
                for f in factors:
                    f["lineage"] = {
                        "parent": parents[0]["name"] if parents else None,
                        "generation": generation,
                        "method": "evolution",
                    }
                return factors
        except Exception:
            logger.exception("Factor evolution failed for generation %d", generation)
        return []

    async def _evaluate_factors(self, factors: list[dict], symbols: list[str], task: dict) -> list[dict]:
        from quantclaw.sandbox.sandbox import Sandbox

        sandbox = Sandbox(config=self._config)

        # Fetch actual DataFrames for sandbox evaluation
        data = await self._fetch_data(symbols, task)

        evaluated = []

        for factor in factors:
            code = factor.get("code", "")
            if not code:
                continue

            eval_script = self._build_eval_script(factor, symbols)
            try:
                result = await sandbox.execute_code(eval_script, timeout=30, data=data)
                if result.status == "ok" and result.result:
                    factor = {**factor, "metrics": result.result}
                else:
                    factor = {**factor, "metrics": {"ic": 0, "rank_ic": 0, "turnover": 0, "sharpe": 0}}
                factor = {**factor, "lineage": factor.get("lineage", {
                    "parent": None, "generation": 0, "method": "exploration",
                })}
                evaluated.append(factor)
            except Exception:
                logger.exception("Factor evaluation failed for %s", factor.get("name", "?"))
                factor = {**factor, "metrics": {"ic": 0, "rank_ic": 0, "turnover": 0, "sharpe": 0}}
                evaluated.append(factor)

        return evaluated

    async def _fetch_data(self, symbols: list[str], task: dict) -> dict:
        """Fetch DataFrames for sandbox evaluation, including extra fields."""
        if not symbols:
            return {}

        # Determine what extra fields to fetch
        extra_fields = self._extract_extra_fields_from_upstream(task)

        try:
            from quantclaw.agents.market_data import load_market_data
            import asyncio as _asyncio

            start = task.get("start") or None
            end = task.get("end") or datetime.now(timezone.utc).date().isoformat()
            # Sync data plugins — to_thread keeps the loop responsive
            # while the miner step pulls per-symbol OHLCV.
            bundle = await _asyncio.to_thread(
                load_market_data,
                self._config,
                symbols,
                start,
                end,
                extra_fields=extra_fields,
            )
            return bundle.frames
        except Exception:
            logger.exception("Data plugin initialization failed")
            return {}

    def _extract_extra_fields_from_upstream(self, task: dict) -> list[str]:
        """Get extra field names from upstream Ingestor's columns list."""
        base = {"open", "high", "low", "close", "volume"}
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict) and "columns" in data:
                cols = data["columns"]
                if isinstance(cols, list):
                    return [c for c in cols if c not in base]
        return []

    def _extract_history_context(self, task: dict) -> str:
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if not isinstance(data, dict):
                continue
            availability = data.get("availability", {})
            summary = availability.get("summary", {}) if isinstance(availability, dict) else {}
            if not summary:
                continue

            parts = []
            price_window = summary.get("price_common_window", {})
            if price_window:
                parts.append(
                    "Common price history across the requested universe runs from "
                    f"{price_window.get('start')} to {price_window.get('end')} "
                    f"({price_window.get('days', 0)} days)."
                )

            recommended = summary.get("recommended_common_window", {})
            if recommended and recommended != price_window:
                parts.append(
                    "When you use shorter-history time-series fields, the effective common "
                    f"window narrows to {recommended.get('start')} through {recommended.get('end')} "
                    f"({recommended.get('days', 0)} days)."
                )

            limiting_fields = summary.get("limiting_fields", [])
            if limiting_fields:
                parts.append(
                    "The shortest-history time-series fields currently limiting lookback are: "
                    + ", ".join(limiting_fields) + "."
                )

            limiting_symbols = summary.get("limiting_symbols", [])
            if limiting_symbols:
                parts.append(
                    "The symbols currently limiting shared price history are: "
                    + ", ".join(limiting_symbols) + "."
                )

            if parts:
                return "\n".join(parts)
        return ""

    def _build_eval_script(self, factor: dict, symbols: list[str]) -> str:
        code = factor["code"]
        symbols_json = json.dumps(symbols)

        return f'''import pandas as pd
import numpy as np
import json
from pathlib import Path

data = {{}}
data_dir = Path("data")
if data_dir.exists():
    for f in data_dir.glob("*.parquet"):
        if f.stem in {symbols_json}:
            data[f.stem] = pd.read_parquet(f)

scores = {{}}
for symbol, df in data.items():
    try:
        result = {code}
        if isinstance(result, pd.Series):
            scores[symbol] = result
    except Exception:
        pass

from quantclaw.sandbox.factor_evaluator import evaluate_factor
metrics = evaluate_factor(scores, data, forward_period=5)
print(json.dumps(metrics))
'''
