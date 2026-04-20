"""Validator: strategy replay + held-out validation in one agent.

Merged from the former Backtester and Evaluator agents. Supports two
task modes:

* ``task="backtest"`` — in-sample replay only. Produces the Sharpe,
  drawdown, turnover metrics that the backtester used to return.
* ``task="validate"`` (default) — runs the in-sample backtest AND an
  independent held-out backtest on the last ``held_out_months`` of the
  date range. Returns a verdict comparing the two to flag overfitting.

Both modes are code-only (no LLM). Both run through the sandbox.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ValidatorAgent(BaseAgent):
    name = "validator"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        strategy_code = task.get("strategy_code", "") or self._extract_strategy_code(task)
        if not strategy_code:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="No strategy_code provided. Pass directly or via upstream Trainer step.",
            )

        task_mode = (task.get("task") or "validate").lower()
        # Legacy task names from the pre-merge workflows still work:
        if task_mode in ("evaluate",):
            task_mode = "backtest"

        if task_mode == "backtest":
            return await self._run_backtest_only(task, strategy_code)
        return await self._run_full_validation(task, strategy_code)

    # ──────────────────────────────────────────────────────────────
    # Backtest-only (former Backtester behavior)
    # ──────────────────────────────────────────────────────────────

    async def _run_backtest_only(self, task: dict, strategy_code: str) -> AgentResult:
        sandbox_enabled = self._config.get("sandbox", {}).get("enabled", True)
        if not sandbox_enabled:
            strategy = task.get("strategy", "")
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={"strategy": strategy, "status": "backtested"},
            )

        symbols = task.get("symbols", [])
        start = task.get("start") or None
        end = task.get("end") or datetime.now(timezone.utc).date().isoformat()

        result = await self._sandbox_replay(strategy_code, symbols, start, end)
        if result is None:
            return AgentResult(status=AgentStatus.FAILED, error="Backtest failed in sandbox")
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={**result, "strategy_code": strategy_code},
        )

    # ──────────────────────────────────────────────────────────────
    # Full validation (former Evaluator behavior, with in-sample run baked in)
    # ──────────────────────────────────────────────────────────────

    async def _run_full_validation(self, task: dict, strategy_code: str) -> AgentResult:
        symbols = task.get("symbols", [])
        full_end = task.get("end") or datetime.now(timezone.utc).date().isoformat()
        full_start = task.get("start") or ""
        held_out_months = task.get(
            "held_out_months",
            self._config.get("contracts", {}).get("held_out_months", 3),
        )

        # Held-out window: last N months of the requested range.
        try:
            end_date = datetime.strptime(full_end, "%Y-%m-%d")
            held_out_start = end_date - relativedelta(months=held_out_months)
            held_out_start_str = held_out_start.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            held_out_start_str = full_start or full_end
            logger.warning("Could not parse end date '%s', using full range", full_end)

        # In-sample: prefer upstream Backtester/Trainer metrics if present;
        # only run our own in-sample backtest when nothing upstream has them.
        in_sample = self._extract_in_sample_metrics(task)
        if not in_sample:
            ran = await self._sandbox_replay(strategy_code, symbols, full_start or None, full_end)
            in_sample = ran or {}

        held_out_result = await self._sandbox_replay(
            strategy_code, symbols, held_out_start_str, full_end,
        )
        if held_out_result is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="Held-out backtest failed to execute",
            )

        in_sample_sharpe = self._to_float(in_sample.get("sharpe", 0))
        held_out_sharpe = self._to_float(held_out_result.get("sharpe", 0))
        degradation_ratio = held_out_sharpe / in_sample_sharpe if in_sample_sharpe > 0 else 0.0

        contract = task.get("_contract", self._config.get("contracts", {}))
        min_held_out_sharpe = float(contract.get("min_held_out_sharpe", 0.0))
        min_trades = int(contract.get("min_trades", 10))
        held_out_trades = int(held_out_result.get("total_trades", 0))

        if held_out_sharpe < 0:
            verdict = "no_edge"
            reason = f"Negative held-out Sharpe ({held_out_sharpe:.2f})"
        elif held_out_trades < min_trades:
            verdict = "insufficient_trades"
            reason = f"Only {held_out_trades} trades in held-out period (need {min_trades})"
        elif degradation_ratio < 0.5 and in_sample_sharpe > 0:
            verdict = "overfit"
            reason = (f"Held-out Sharpe ({held_out_sharpe:.2f}) is "
                      f"{degradation_ratio:.0%} of in-sample ({in_sample_sharpe:.2f})")
        elif held_out_sharpe < min_held_out_sharpe:
            verdict = "below_contract"
            reason = f"Held-out Sharpe {held_out_sharpe:.2f} below contract minimum {min_held_out_sharpe}"
        else:
            verdict = "validated"
            reason = (f"Held-out Sharpe {held_out_sharpe:.2f} "
                      f"({degradation_ratio:.0%} of in-sample {in_sample_sharpe:.2f})")

        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "verdict": verdict,
                "reason": reason,
                # Full-suite metrics — what the allocator and reporter consume.
                "sharpe": round(in_sample_sharpe, 3),
                "annual_return": round(self._to_float(in_sample.get("annual_return", 0)), 4),
                "max_drawdown": round(self._to_float(in_sample.get("max_drawdown", 0)), 4),
                "held_out_sharpe": round(held_out_sharpe, 3),
                "held_out_return": round(self._to_float(held_out_result.get("annual_return", 0)), 4),
                "held_out_drawdown": round(self._to_float(held_out_result.get("max_drawdown", 0)), 4),
                "held_out_trades": held_out_trades,
                "held_out_win_rate": round(self._to_float(held_out_result.get("win_rate", 0)), 3),
                "held_out_period": f"{held_out_start_str} to {full_end}",
                "in_sample_sharpe": round(in_sample_sharpe, 3),
                "degradation_ratio": round(degradation_ratio, 2),
                "strategy_code": strategy_code,
            },
        )

    # ──────────────────────────────────────────────────────────────
    # Shared sandbox replay
    # ──────────────────────────────────────────────────────────────

    async def _sandbox_replay(
        self,
        strategy_code: str,
        symbols: list[str],
        start: str | None,
        end: str,
    ) -> dict | None:
        """Replay ``strategy_code`` against market data in the sandbox.

        Returns the parsed metrics dict on success, or None on failure.
        """
        try:
            from quantclaw.agents.market_data import (
                extract_required_columns_from_code,
                extra_fields_from_columns,
                load_market_data,
            )
            from quantclaw.sandbox.sandbox import Sandbox

            required_columns = extract_required_columns_from_code(strategy_code)
            extra_fields = extra_fields_from_columns(required_columns)
            bundle = load_market_data(
                self._config,
                symbols,
                start,
                end,
                extra_fields=extra_fields,
            )
            data = bundle.frames
            if not data:
                logger.warning("No data available for %s..%s", start, end)
                return None

            sandbox = Sandbox(config=self._config)
            timeout = self._config.get("sandbox", {}).get("timeout", 60)
            result = await sandbox.execute_strategy(
                strategy_code=strategy_code,
                data=data,
                config={
                    "initial_capital": self._config.get("initial_capital", 100000),
                    "commission_pct": self._config.get("commission_pct", 0.001),
                    "slippage_pct": self._config.get("slippage_pct", 0.0005),
                },
                timeout=timeout,
            )
            if result.status == "ok" and result.result:
                return result.result
            logger.warning(
                "Sandbox replay failed: %s",
                (result.stderr or "")[:300] if hasattr(result, "stderr") else "unknown",
            )
            return None
        except Exception:
            logger.exception("Validator sandbox replay failed")
            return None

    # ──────────────────────────────────────────────────────────────
    # Upstream extraction
    # ──────────────────────────────────────────────────────────────

    def _extract_strategy_code(self, task: dict) -> str:
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict) and "strategy_code" in data:
                return data["strategy_code"]
        return ""

    def _extract_in_sample_metrics(self, task: dict) -> dict:
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict):
                if "sharpe" in data and "annual_return" in data:
                    return data
                if "sharpe" in data and "model_type" in data:
                    return data
        return {}

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
