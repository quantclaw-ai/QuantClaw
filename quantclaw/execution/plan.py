"""Plan data structure and approval flow."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum


class PlanStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    SKIPPED = "skipped"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class PlanStep:
    id: int
    agent: str
    task: dict
    description: str
    depends_on: list[int] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING


@dataclass
class Plan:
    id: str
    description: str
    steps: list[PlanStep]
    status: PlanStatus = PlanStatus.PROPOSED
    results: dict = field(default_factory=dict)  # step_id -> AgentResult
    contract: dict = field(default_factory=dict)

    def approve_all(self):
        self.status = PlanStatus.APPROVED
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.APPROVED

    def approve_step(self, step_id: int):
        for step in self.steps:
            if step.id == step_id:
                step.status = StepStatus.APPROVED

    def skip_step(self, step_id: int):
        for step in self.steps:
            if step.id == step_id:
                step.status = StepStatus.SKIPPED

    def reject(self):
        self.status = PlanStatus.REJECTED

    def get_ready_steps(self) -> list[PlanStep]:
        """Return steps that are approved and whose dependencies are completed."""
        completed_ids = {s.id for s in self.steps
                         if s.status == StepStatus.COMPLETED}
        ready = []
        for step in self.steps:
            if step.status != StepStatus.APPROVED:
                continue
            if all(dep_id in completed_ids for dep_id in step.depends_on):
                ready.append(step)
        return ready

    def is_complete(self) -> bool:
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in self.steps
        )

    def validate(self) -> list[str]:
        """Validate plan DAG. Returns list of error messages."""
        errors = []
        step_ids = {s.id for s in self.steps}

        # Check for invalid dependency references
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in step_ids:
                    errors.append(f"Step {s.id} depends on non-existent step {dep}")

        # Check for cycles using DFS
        visited: set[int] = set()
        path: set[int] = set()

        def has_cycle(step_id: int) -> bool:
            if step_id in path:
                return True
            if step_id in visited:
                return False
            visited.add(step_id)
            path.add(step_id)
            step = next((s for s in self.steps if s.id == step_id), None)
            if step:
                for dep in step.depends_on:
                    if has_cycle(dep):
                        return True
            path.discard(step_id)
            return False

        for s in self.steps:
            if has_cycle(s.id):
                errors.append(f"Circular dependency detected involving step {s.id}")
                break

        return errors

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "steps": [
                {
                    "id": s.id,
                    "agent": s.agent,
                    "description": s.description,
                    "status": s.status.value,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
        }
