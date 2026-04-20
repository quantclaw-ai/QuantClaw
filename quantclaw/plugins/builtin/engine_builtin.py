"""Built-in lightweight backtest engine with realistic transaction costs."""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from quantclaw.plugins.interfaces import EnginePlugin, BacktestResult

logger = logging.getLogger(__name__)


class BuiltinEnginePlugin(EnginePlugin):
    name = "engine_builtin"

    def backtest(
        self,
        strategy,
        data: dict[str, pd.DataFrame],
        config: dict,
    ) -> BacktestResult:
        commission_pct = config.get("commission_pct", 0.001)
        slippage_pct = config.get("slippage_pct", 0.0005)
        initial_capital = config.get("initial_capital", 100000)
        freq = getattr(strategy, "frequency", "weekly")

        all_dates = sorted(set().union(*(df.index for df in data.values())))
        if freq == "daily":
            rebalance_dates = all_dates
        elif freq == "weekly":
            rebalance_dates = [d for d in all_dates if d.weekday() == 0]
        elif freq == "monthly":
            # First trading day of each month
            seen_months = set()
            rebalance_dates = []
            for d in all_dates:
                month_key = (d.year, d.month)
                if month_key not in seen_months:
                    seen_months.add(month_key)
                    rebalance_dates.append(d)
        else:
            rebalance_dates = all_dates

        from quantclaw.strategy.audit import BacktestAudit
        audit = BacktestAudit(
            strategy_name=getattr(strategy, 'name', 'unnamed'),
            start_date=str(all_dates[0].date()) if all_dates else '',
            end_date=str(all_dates[-1].date()) if all_dates else '',
        )

        cash = initial_capital
        positions: dict[str, float] = {}
        equity_curve: list[dict] = []
        trades: list[dict] = []
        peak_equity = initial_capital
        signal_errors = 0

        class DataProxy:
            def __init__(self, all_data, current_date):
                self._data = all_data
                self._date = current_date

            def history(self, symbol, bars=60):
                if symbol not in self._data:
                    return pd.DataFrame()
                df = self._data[symbol]
                return df[df.index <= self._date].tail(bars)

        class PortfolioProxy:
            def __init__(self, eq, dd):
                self.equity = eq
                self.drawdown = dd

        for date in all_dates:
            portfolio_value = cash
            for sym, qty in positions.items():
                if sym in data and date in data[sym].index:
                    portfolio_value += qty * data[sym].loc[date, "close"]

            peak_equity = max(peak_equity, portfolio_value)
            drawdown = (portfolio_value - peak_equity) / peak_equity
            equity_curve.append({"date": date, "equity": portfolio_value})

            if date not in rebalance_dates:
                continue

            proxy = DataProxy(data, date)
            portfolio = PortfolioProxy(portfolio_value, drawdown)

            date_str = str(date.date()) if hasattr(date, 'date') else str(date)

            try:
                signals = strategy.signals(proxy)
                strategy_signal_errors = len(getattr(strategy, "_last_signal_errors", []) or [])
                if strategy_signal_errors:
                    signal_errors += strategy_signal_errors
                    if signal_errors <= 3:
                        logger.warning(
                            "Strategy reported %d symbol-level signal errors on %s",
                            strategy_signal_errors,
                            date_str,
                        )
                audit.add_signal(date_str, signals)
                target_weights = strategy.allocate(signals, portfolio)
                audit.add_allocation(date_str, target_weights)
            except Exception as exc:
                signal_errors += 1
                if signal_errors <= 3:
                    logger.warning("Signal error on %s: %s", date_str, exc)
                continue

            if hasattr(strategy, "risk_check"):
                try:
                    if not strategy.risk_check(None, portfolio):
                        audit.add_skip(date_str, "risk_check_failed")
                        continue
                    audit.add_risk_check(date_str, True, drawdown)
                except Exception as exc:
                    logger.warning("Risk check error on %s: %s", date_str, exc)
                    continue

            for sym, target_wt in target_weights.items():
                if sym not in data or date not in data[sym].index:
                    continue
                price = data[sym].loc[date, "close"]
                target_value = portfolio_value * target_wt
                current_qty = positions.get(sym, 0)
                diff_value = target_value - current_qty * price
                if abs(diff_value) < 100:
                    continue
                trade_qty = diff_value / price
                fill_price = price * (
                    1 + slippage_pct if trade_qty > 0 else 1 - slippage_pct
                )
                cost = abs(trade_qty * fill_price) * commission_pct
                positions[sym] = current_qty + trade_qty
                cash -= trade_qty * fill_price + cost
                side = "buy" if trade_qty > 0 else "sell"
                trades.append({
                    "date": date,
                    "symbol": sym,
                    "qty": trade_qty,
                    "price": fill_price,
                    "cost": cost,
                    "side": side,
                })
                audit.add_trade(date_str, sym, trade_qty, fill_price, side, cost)

            for sym in list(positions.keys()):
                if sym not in target_weights and positions[sym] != 0:
                    if sym in data and date in data[sym].index:
                        price = data[sym].loc[date, "close"]
                        fill_price = price * (1 - slippage_pct)
                        cost = abs(positions[sym] * fill_price) * commission_pct
                        sell_qty = -positions[sym]
                        cash += positions[sym] * fill_price - cost
                        trades.append({
                            "date": date,
                            "symbol": sym,
                            "qty": sell_qty,
                            "price": fill_price,
                            "cost": cost,
                            "side": "sell",
                        })
                        audit.add_trade(date_str, sym, sell_qty, fill_price, "sell", cost)
                        positions[sym] = 0

        if signal_errors > 0:
            logger.warning(
                "Strategy had %d signal errors across %d rebalance dates",
                signal_errors, len(rebalance_dates),
            )

        eq_df = pd.DataFrame(equity_curve).set_index("date")["equity"]
        returns = eq_df.pct_change().dropna()

        if len(returns) < 2:
            return BacktestResult(
                equity_curve=eq_df,
                trades=pd.DataFrame(trades),
                sharpe=0,
                annual_return=0,
                max_drawdown=0,
                total_trades=len(trades),
                win_rate=0,
                metadata={"engine": "builtin", "commission": commission_pct, "slippage": slippage_pct, "signal_errors": signal_errors, "audit": audit},
            )

        ann_return = (eq_df.iloc[-1] / eq_df.iloc[0]) ** (252 / len(returns)) - 1
        ann_vol = returns.std() * np.sqrt(252)
        sharpe = ann_return / ann_vol if ann_vol > 1e-8 else 0
        peak = eq_df.cummax()
        max_dd = float(((eq_df - peak) / peak).min())
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        # Calculate win rate from round-trip P&L (FIFO matching)
        position_costs: dict[str, list[float]] = {}
        winning_trades = 0
        closed_trades = 0
        for t in trades:
            sym = t.get("symbol", "")
            qty = t.get("qty", 0)
            price = t.get("price", 0)
            if qty > 0:  # buy
                position_costs.setdefault(sym, []).append(price)
            elif qty < 0 and sym in position_costs and position_costs[sym]:  # sell
                entry_price = position_costs[sym].pop(0)  # FIFO
                if price > entry_price:
                    winning_trades += 1
                closed_trades += 1
        win_rate = winning_trades / closed_trades if closed_trades > 0 else 0

        return BacktestResult(
            equity_curve=eq_df,
            trades=trades_df,
            sharpe=round(sharpe, 3),
            annual_return=round(ann_return, 4),
            max_drawdown=round(max_dd, 4),
            total_trades=len(trades),
            win_rate=round(win_rate, 3),
            metadata={
                "engine": "builtin",
                "commission": commission_pct,
                "slippage": slippage_pct,
                "signal_errors": signal_errors,
                "audit": audit,
            },
        )
