"""Executor: trade execution with paper trading and real broker support.

Paper trades by default. Live execution requires an explicit config flag and
a broker plugin.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ExecutorAgent(BaseAgent):
    name = "executor"
    model = "opus"
    daemon = False

    def __init__(self, bus, config):
        super().__init__(bus, config)
        initial = config.get("initial_capital", 100000)
        self._paper_portfolio = {
            "cash": initial,
            "positions": {},
            "initial_capital": initial,
        }

    async def execute(self, task: dict) -> AgentResult:
        task_type = task.get("task", "")
        orders = task.get("orders", [])
        strategy_path = task.get("strategy_path", "")

        if task_type == "run_deployments":
            return await self._run_paper_deployments(task)

        execution_config = self._config.get("execution", {})
        use_real_broker = bool(execution_config.get("live_trading_enabled")) and self._has_broker()

        # Run compliance check — blocks live trades, warns for paper
        compliance_result = await self._check_compliance(orders)
        if compliance_result and not compliance_result.get("compliant", True):
            if use_real_broker:
                violations = compliance_result.get("violations", [])
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error=f"Compliance rejected: {[v['rule'] for v in violations]}",
                    data={"compliance": compliance_result, "orders_rejected": orders},
                )
            logger.warning("Compliance violations in paper mode: %s",
                           compliance_result.get("violations", []))

        if use_real_broker:
            return await self._execute_live(orders)

        return await self._execute_paper(orders, strategy_path)

    async def _run_paper_deployments(self, task: dict) -> AgentResult:
        """Run active paper deployments, aggregate target weights, and submit paper orders."""
        from quantclaw.agents.market_data import (
            extract_required_columns_from_code,
            extra_fields_from_columns,
        )

        deployments = [
            deployment for deployment in task.get("deployments", [])
            if deployment.get("strategy_path")
        ]
        if not deployments:
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={
                    "mode": "paper",
                    "message": "No active paper deployments to run.",
                    "orders_executed": 0,
                    "deployment_updates": [],
                    "portfolio": {
                        "cash": self._paper_portfolio["cash"],
                        "positions": dict(self._paper_portfolio["positions"]),
                        "equity": self._paper_portfolio["cash"],
                    },
                },
            )

        lookback_days = int(task.get("lookback_days", 180))
        end = task.get("end") or datetime.now(timezone.utc).date().isoformat()
        start = task.get("start") or (
            datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
        ).isoformat()

        aggregate_weights: dict[str, float] = {}
        latest_prices: dict[str, float] = {}
        deployment_updates: list[dict] = []

        for deployment in deployments:
            strategy_path = deployment.get("strategy_path", "")
            if not strategy_path:
                continue
            try:
                strategy = self._load_strategy(strategy_path)
            except Exception as exc:
                logger.warning("Could not load deployment %s: %s", strategy_path, exc)
                deployment_updates.append({
                    "deployment_id": deployment.get("id", ""),
                    "strategy_path": strategy_path,
                    "status": "failed",
                    "error": str(exc),
                })
                continue

            symbols = list(getattr(strategy, "universe", []) or deployment.get("symbols", []) or [])
            if not symbols:
                deployment_updates.append({
                    "deployment_id": deployment.get("id", ""),
                    "strategy_path": strategy_path,
                    "status": "failed",
                    "error": "Strategy has no universe",
                })
                continue

            required_columns = list(getattr(strategy, "required_columns", []) or [])
            extra_fields = list(getattr(strategy, "_extra_fields", []) or [])
            if not extra_fields and required_columns:
                extra_fields = extra_fields_from_columns(required_columns)
            if not extra_fields and strategy_path:
                try:
                    from pathlib import Path

                    source = Path(strategy_path).read_text(encoding="utf-8")
                    extra_fields = extra_fields_from_columns(
                        extract_required_columns_from_code(source)
                    )
                except Exception:
                    logger.debug("Could not infer extra fields from %s", strategy_path)

            # ``_load_market_data`` calls into data plugins that use sync
            # ``requests.get``; running it inline here would block the
            # asyncio event loop for the duration of every fetch (same
            # bug pattern as the WorldBank fix in ingestor.py).
            import asyncio as _asyncio
            data = await _asyncio.to_thread(
                self._load_market_data, symbols, start, end, extra_fields=extra_fields,
            )
            if not data:
                deployment_updates.append({
                    "deployment_id": deployment.get("id", ""),
                    "strategy_path": strategy_path,
                    "status": "failed",
                    "error": "No market data available",
                })
                continue

            current_date = max(df.index.max() for df in data.values() if not df.empty)
            if current_date is None:
                continue

            data_proxy = _StrategyDataProxy(data, current_date)
            portfolio_value = self._estimate_portfolio_value(data)
            portfolio_proxy = SimpleNamespace(
                equity=portfolio_value,
                drawdown=self._estimate_drawdown(portfolio_value),
            )

            try:
                signals = strategy.signals(data_proxy)
                target_weights = strategy.allocate(signals, portfolio_proxy) or {}
            except Exception as exc:
                logger.warning("Deployment signal generation failed for %s: %s", strategy_path, exc)
                deployment_updates.append({
                    "deployment_id": deployment.get("id", ""),
                    "strategy_path": strategy_path,
                    "status": "failed",
                    "error": str(exc),
                })
                continue

            signal_errors = len(getattr(strategy, "_last_signal_errors", []) or [])
            if signal_errors:
                logger.warning(
                    "Deployment %s had %d symbol-level signal errors",
                    strategy_path,
                    signal_errors,
                )

            allocation_pct = self._to_float(deployment.get("allocation_pct", 0.0))
            if allocation_pct <= 0:
                allocation_pct = 1.0 / max(len(deployments), 1)

            scaled_weights: dict[str, float] = {}
            for symbol, weight in (target_weights or {}).items():
                try:
                    scaled = float(weight) * allocation_pct
                except (TypeError, ValueError):
                    continue
                if scaled <= 0:
                    continue
                scaled_weights[symbol] = scaled_weights.get(symbol, 0.0) + scaled
                aggregate_weights[symbol] = aggregate_weights.get(symbol, 0.0) + scaled
                if symbol in data and not data[symbol].empty:
                    latest_prices[symbol] = float(data[symbol]["close"].iloc[-1])

            deployment_updates.append({
                "deployment_id": deployment.get("id", ""),
                "strategy_path": strategy_path,
                "status": "ok",
                "symbols": symbols,
                "signal_errors": signal_errors,
                "target_weights": {k: round(v, 4) for k, v in scaled_weights.items()},
                "latest_date": str(current_date.date()) if hasattr(current_date, "date") else str(current_date),
            })

        self._normalize_weights(aggregate_weights)
        orders = self._build_orders_from_target_weights(aggregate_weights, latest_prices)
        result = await self._execute_paper(orders, strategy_path="")
        if result.status != AgentStatus.SUCCESS:
            return result

        result.data["deployment_updates"] = deployment_updates
        result.data["deployments_run"] = [
            update["deployment_id"] for update in deployment_updates if update.get("status") == "ok"
        ]
        result.data["signal_errors"] = sum(
            int(update.get("signal_errors", 0) or 0)
            for update in deployment_updates
        )
        result.data["aggregate_target_weights"] = {
            symbol: round(weight, 4) for symbol, weight in aggregate_weights.items()
        }
        result.data["latest_prices"] = latest_prices
        result.data["paper_mode"] = True
        return result

    async def _execute_paper(self, orders: list[dict], strategy_path: str) -> AgentResult:
        """Paper trade — track virtual positions and portfolio state."""
        executed = []
        skipped = []
        timestamp = datetime.now(timezone.utc).isoformat()
        portfolio = self._paper_portfolio

        for order in orders:
            symbol = order.get("symbol", "")
            side = order.get("side", "buy")
            qty = order.get("qty", 0)
            price = order.get("price", 0)

            if not symbol:
                continue

            order_value = qty * price

            if side == "buy":
                if portfolio["cash"] < order_value:
                    logger.warning(
                        "Insufficient cash for %s %s: need %.2f, have %.2f",
                        side, symbol, order_value, portfolio["cash"],
                    )
                    skipped.append({
                        "symbol": symbol, "side": side, "qty": qty, "price": price,
                        "reason": "insufficient_cash",
                    })
                    continue
                portfolio["cash"] -= order_value
                portfolio["positions"][symbol] = portfolio["positions"].get(symbol, 0) + qty
            elif side == "sell":
                current_qty = portfolio["positions"].get(symbol, 0)
                if current_qty < qty:
                    logger.warning(
                        "Insufficient positions for %s %s: need %d, have %d",
                        side, symbol, qty, current_qty,
                    )
                    skipped.append({
                        "symbol": symbol, "side": side, "qty": qty, "price": price,
                        "reason": "insufficient_positions",
                    })
                    continue
                portfolio["cash"] += order_value
                portfolio["positions"][symbol] = current_qty - qty
                if portfolio["positions"][symbol] == 0:
                    del portfolio["positions"][symbol]

            fill = {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "fill_price": price,  # Paper trade fills at requested price
                "status": "filled",
                "mode": "paper",
                "timestamp": timestamp,
            }
            executed.append(fill)

        # Emit trade filled events
        from quantclaw.events.types import Event, EventType
        for order in executed:
            await self._bus.publish(Event(
                type=EventType.TRADE_ORDER_FILLED,
                payload=order,
                source_agent="executor",
            ))

        # Calculate equity (cash + position values at last fill prices)
        position_value = sum(
            qty * next(
                (o.get("price", 0) for o in orders if o.get("symbol") == sym),
                0,
            )
            for sym, qty in portfolio["positions"].items()
        )
        equity = portfolio["cash"] + position_value

        if not executed and not orders:
            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={
                    "mode": "paper",
                    "message": "Paper trading mode active. No orders to execute.",
                    "strategy_path": strategy_path,
                    "orders_executed": 0,
                    "portfolio": {
                        "cash": portfolio["cash"],
                        "positions": dict(portfolio["positions"]),
                        "equity": equity,
                    },
                },
            )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "mode": "paper",
                "orders_executed": len(executed),
                "orders": executed,
                "skipped": skipped,
                "strategy_path": strategy_path,
                "portfolio": {
                    "cash": portfolio["cash"],
                    "positions": dict(portfolio["positions"]),
                    "equity": equity,
                },
            },
        )

    async def _execute_live(self, orders: list[dict]) -> AgentResult:
        """Execute via real broker plugin."""
        try:
            from quantclaw.plugins.manager import PluginManager
            pm = PluginManager()
            pm.discover()
            broker_name = self._config.get("plugins", {}).get("broker", "broker_ib")
            broker = pm.get("broker", broker_name)

            if broker is None:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error=f"Broker plugin not found: {broker_name}",
                )

            executed = []
            for order in orders:
                try:
                    result = broker.submit_order(
                        symbol=order.get("symbol", ""),
                        side=order.get("side", "buy"),
                        qty=order.get("qty", 0),
                        order_type=order.get("order_type", "market"),
                    )
                    executed.append({**order, "status": "submitted", "result": result, "mode": "live"})
                except Exception as e:
                    logger.exception("Order submission failed for %s", order.get("symbol", "?"))
                    executed.append({**order, "status": "failed", "error": str(e), "mode": "live"})

            return AgentResult(
                status=AgentStatus.SUCCESS,
                data={
                    "mode": "live",
                    "orders_executed": len(executed),
                    "orders": executed,
                },
            )
        except Exception as e:
            logger.exception("Live execution failed")
            return AgentResult(status=AgentStatus.FAILED, error=str(e))

    async def _check_compliance(self, orders: list[dict]) -> dict | None:
        """Run compliance checks on proposed orders."""
        try:
            from quantclaw.agents.compliance import ComplianceAgent
            compliance = ComplianceAgent(self._bus, self._config)
            portfolio = self._paper_portfolio
            result = await compliance.execute({
                "trades": [
                    {
                        "symbol": o.get("symbol", ""),
                        "value": abs(o.get("qty", 0) * o.get("price", 0)),
                    }
                    for o in orders
                ],
                "portfolio_value": portfolio["cash"] + sum(
                    qty * orders[0].get("price", 0) if orders else 0
                    for qty in portfolio["positions"].values()
                ),
                "current_drawdown": (
                    portfolio["cash"]
                    + sum(portfolio["positions"].values())
                    - portfolio["initial_capital"]
                ) / portfolio["initial_capital"],
            })
            return result.data
        except Exception:
            logger.debug("Compliance check skipped")
            return None

    def _load_strategy(self, strategy_path: str):
        from quantclaw.strategy.loader import load_strategy

        return load_strategy(strategy_path)

    def _load_market_data(
        self,
        symbols: list[str],
        start: str,
        end: str,
        *,
        extra_fields: list[str] | None = None,
    ) -> dict:
        from quantclaw.agents.market_data import load_market_data

        bundle = load_market_data(
            self._config,
            symbols,
            start,
            end,
            extra_fields=extra_fields,
        )
        return bundle.frames

    def _estimate_portfolio_value(self, data: dict) -> float:
        cash = self._paper_portfolio["cash"]
        positions = self._paper_portfolio["positions"]
        value = cash
        for symbol, qty in positions.items():
            df = data.get(symbol)
            if df is None or df.empty:
                continue
            value += qty * float(df["close"].iloc[-1])
        return value

    def _estimate_drawdown(self, portfolio_value: float) -> float:
        initial = self._paper_portfolio.get("initial_capital", 0) or 1
        return (portfolio_value - initial) / initial

    def _normalize_weights(self, weights: dict[str, float]) -> None:
        total = sum(weight for weight in weights.values() if weight > 0)
        if total <= 1.0 or total <= 0:
            return
        for symbol in list(weights.keys()):
            weights[symbol] = weights[symbol] / total

    def _build_orders_from_target_weights(
        self,
        target_weights: dict[str, float],
        latest_prices: dict[str, float],
    ) -> list[dict]:
        portfolio_value = self._paper_portfolio["cash"]
        for symbol, qty in self._paper_portfolio["positions"].items():
            price = latest_prices.get(symbol)
            if price:
                portfolio_value += qty * price

        orders: list[dict] = []
        min_order_value = float(self._config.get("campaigns", {}).get("min_rebalance_order_value", 100.0))
        all_symbols = set(target_weights) | set(self._paper_portfolio["positions"])
        for symbol in all_symbols:
            price = latest_prices.get(symbol)
            if not price:
                continue
            target_value = portfolio_value * max(target_weights.get(symbol, 0.0), 0.0)
            current_qty = self._paper_portfolio["positions"].get(symbol, 0)
            current_value = current_qty * price
            diff_value = target_value - current_value
            if abs(diff_value) < min_order_value:
                continue
            qty = int(abs(diff_value) / price)
            if qty <= 0:
                continue
            orders.append({
                "symbol": symbol,
                "side": "buy" if diff_value > 0 else "sell",
                "qty": qty,
                "price": round(price, 4),
            })
        return orders

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _has_broker(self) -> bool:
        """Check if a real broker is configured."""
        broker = self._config.get("plugins", {}).get("broker", "")
        return bool(broker)


class _StrategyDataProxy:
    def __init__(self, all_data: dict, current_date):
        self._data = all_data
        self._date = current_date

    def history(self, symbol, bars=60):
        import pandas as pd

        if symbol not in self._data:
            return pd.DataFrame()
        df = self._data[symbol]
        return df[df.index <= self._date].tail(bars)
