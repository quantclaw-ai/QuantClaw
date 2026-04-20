"""Task CRUD operations."""
from __future__ import annotations
from enum import StrEnum
from quantclaw.state.db import StateDB

class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskStore:
    def __init__(self, db: StateDB):
        self._db = db

    async def create(self, agent: str, command: str, status: TaskStatus = TaskStatus.PENDING) -> int:
        cursor = await self._db.conn.execute(
            "INSERT INTO tasks (agent, command, status) VALUES (?, ?, ?)",
            (agent, command, status.value),
        )
        await self._db.conn.commit()
        return cursor.lastrowid

    async def get(self, task_id: int) -> dict | None:
        cursor = await self._db.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_status(self, task_id: int, status: TaskStatus, result: str = None, error: str = None):
        ts_field = "started_at" if status == TaskStatus.RUNNING else "completed_at" if status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else None
        if ts_field:
            await self._db.conn.execute(
                f"UPDATE tasks SET status = ?, result = ?, error = ?, {ts_field} = CURRENT_TIMESTAMP WHERE id = ?",
                (status.value, result, error, task_id),
            )
        else:
            await self._db.conn.execute(
                "UPDATE tasks SET status = ?, result = ?, error = ? WHERE id = ?",
                (status.value, result, error, task_id),
            )
        await self._db.conn.commit()

    async def list_by_status(self, status: TaskStatus) -> list[dict]:
        cursor = await self._db.conn.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status.value,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def list_today(self) -> list[dict]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM tasks WHERE date(created_at) = date('now') ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
