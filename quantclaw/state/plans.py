"""Plan persistence: save and restore plans from SQLite."""
from __future__ import annotations
import json
from quantclaw.state.db import StateDB
from quantclaw.execution.plan import Plan, PlanStep, PlanStatus, StepStatus


class PlanStore:
    def __init__(self, db: StateDB):
        self._db = db

    async def save(self, plan: Plan) -> None:
        steps_json = json.dumps([
            {"id": s.id, "agent": s.agent, "task": s.task,
             "description": s.description, "depends_on": s.depends_on,
             "status": s.status.value}
            for s in plan.steps
        ])
        await self._db.conn.execute(
            """INSERT OR REPLACE INTO plans (id, description, steps_json, status, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (plan.id, plan.description, steps_json, plan.status.value),
        )
        await self._db.conn.commit()

    async def get(self, plan_id: str) -> Plan | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM plans WHERE id = ?", (plan_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        steps_data = json.loads(row["steps_json"])
        steps = [
            PlanStep(
                id=s["id"], agent=s["agent"], task=s.get("task", {}),
                description=s["description"], depends_on=s.get("depends_on", []),
                status=StepStatus(s["status"]),
            )
            for s in steps_data
        ]
        return Plan(
            id=row["id"], description=row["description"],
            steps=steps, status=PlanStatus(row["status"]),
        )

    async def list_by_status(self, status: PlanStatus) -> list[Plan]:
        cursor = await self._db.conn.execute(
            "SELECT id FROM plans WHERE status = ?", (status.value,)
        )
        rows = await cursor.fetchall()
        plans = []
        for row in rows:
            plan = await self.get(row["id"])
            if plan:
                plans.append(plan)
        return plans

    async def update_status(self, plan_id: str, status: PlanStatus) -> None:
        await self._db.conn.execute(
            "UPDATE plans SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status.value, plan_id),
        )
        await self._db.conn.commit()
