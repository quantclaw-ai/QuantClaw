"""Strategy memory: tracks what worked and what didn't across runs."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from quantclaw.state.db import StateDB

# Add strategy_memory table to schema
MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_type TEXT NOT NULL,
    parameters TEXT NOT NULL,
    sharpe DOUBLE,
    annual_return DOUBLE,
    max_drawdown DOUBLE,
    total_trades INTEGER,
    win_rate DOUBLE,
    universe TEXT,
    frequency TEXT,
    backtest_start TEXT,
    backtest_end TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_anti_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    failure_count INTEGER DEFAULT 1,
    avg_sharpe DOUBLE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class StrategyMemory:
    def __init__(self, db: StateDB):
        self._db = db
        self._initialized = False

    async def _ensure_tables(self):
        if not self._initialized:
            await self._db.conn.executescript(MEMORY_SCHEMA)
            await self._db.conn.commit()
            self._initialized = True

    async def record_result(self, strategy_type: str, parameters: dict,
                            sharpe: float, annual_return: float, max_drawdown: float,
                            total_trades: int = 0, win_rate: float = 0,
                            universe: list[str] = None, frequency: str = "weekly",
                            backtest_start: str = "", backtest_end: str = ""):
        """Record a backtest result for future reference."""
        await self._ensure_tables()
        await self._db.conn.execute(
            """INSERT INTO strategy_memory
               (strategy_type, parameters, sharpe, annual_return, max_drawdown,
                total_trades, win_rate, universe, frequency, backtest_start, backtest_end)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (strategy_type, json.dumps(parameters), sharpe, annual_return, max_drawdown,
             total_trades, win_rate, json.dumps(universe or []), frequency,
             backtest_start, backtest_end),
        )
        await self._db.conn.commit()

        # Check for anti-patterns
        if sharpe < 0:
            await self._record_anti_pattern(strategy_type, parameters, sharpe)

    async def _record_anti_pattern(self, strategy_type: str, parameters: dict, sharpe: float):
        """Track strategies that consistently fail."""
        pattern_key = f"{strategy_type}:{json.dumps(sorted(parameters.items()))}"
        cursor = await self._db.conn.execute(
            "SELECT id, failure_count, avg_sharpe FROM strategy_anti_patterns WHERE pattern = ?",
            (pattern_key,),
        )
        row = await cursor.fetchone()
        if row:
            new_count = row[1] + 1
            new_avg = (row[2] * row[1] + sharpe) / new_count
            await self._db.conn.execute(
                "UPDATE strategy_anti_patterns SET failure_count = ?, avg_sharpe = ? WHERE id = ?",
                (new_count, new_avg, row[0]),
            )
        else:
            await self._db.conn.execute(
                "INSERT INTO strategy_anti_patterns (pattern, failure_count, avg_sharpe, description) VALUES (?, 1, ?, ?)",
                (pattern_key, sharpe, f"{strategy_type} with params {parameters}"),
            )
        await self._db.conn.commit()

    async def get_best_params(self, strategy_type: str, top_n: int = 5) -> list[dict]:
        """Get the best historical parameters for a strategy type."""
        await self._ensure_tables()
        cursor = await self._db.conn.execute(
            """SELECT parameters, sharpe, annual_return, max_drawdown, frequency
               FROM strategy_memory
               WHERE strategy_type = ? AND sharpe > 0
               ORDER BY sharpe DESC LIMIT ?""",
            (strategy_type, top_n),
        )
        rows = await cursor.fetchall()
        return [{
            "parameters": json.loads(r[0]),
            "sharpe": r[1],
            "annual_return": r[2],
            "max_drawdown": r[3],
            "frequency": r[4],
        } for r in rows]

    async def get_anti_patterns(self, min_failures: int = 3) -> list[dict]:
        """Get strategies that have consistently failed."""
        await self._ensure_tables()
        cursor = await self._db.conn.execute(
            """SELECT pattern, failure_count, avg_sharpe, description
               FROM strategy_anti_patterns
               WHERE failure_count >= ?
               ORDER BY failure_count DESC""",
            (min_failures,),
        )
        rows = await cursor.fetchall()
        return [{
            "pattern": r[0],
            "failure_count": r[1],
            "avg_sharpe": r[2],
            "description": r[3],
        } for r in rows]

    async def get_suggestions(self, strategy_type: str) -> dict:
        """Get suggestions based on collective intelligence."""
        await self._ensure_tables()
        best = await self.get_best_params(strategy_type)
        anti = await self.get_anti_patterns()

        # Count total runs for this strategy type
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) FROM strategy_memory WHERE strategy_type = ?",
            (strategy_type,),
        )
        total_runs = (await cursor.fetchone())[0]

        return {
            "strategy_type": strategy_type,
            "total_past_runs": total_runs,
            "best_configurations": best,
            "anti_patterns": [a for a in anti if strategy_type in a.get("pattern", "")],
        }

    async def get_stats(self) -> dict:
        """Get overall strategy memory statistics."""
        await self._ensure_tables()
        cursor = await self._db.conn.execute("SELECT COUNT(*), AVG(sharpe), MAX(sharpe) FROM strategy_memory")
        row = await cursor.fetchone()
        return {
            "total_backtests": row[0] or 0,
            "avg_sharpe": round(row[1] or 0, 3),
            "best_sharpe": round(row[2] or 0, 3),
        }
