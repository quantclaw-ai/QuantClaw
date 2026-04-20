"""Tests for enhanced DAG execution with orchestration events."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool
from quantclaw.execution.plan import Plan, PlanStep, StepStatus


class AccumulatorAgent(BaseAgent):
    """Agent that returns its input plus its own contribution."""
    name = "accumulator"
    model = "sonnet"

    async def execute(self, task: dict) -> AgentResult:
        value = task.get("value", 0)
        upstream = task.get("_upstream_results", {})
        total = value + sum(r.get("value", 0) for r in upstream.values())
        return AgentResult(status=AgentStatus.SUCCESS, data={"value": total})


def _make_pool():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("accumulator", AccumulatorAgent)
    return bus, pool


def test_dag_passes_upstream_results():
    bus, pool = _make_pool()
    dispatcher = Dispatcher(pool=pool, bus=bus)

    plan = Plan(
        id="test-dag",
        description="test upstream passing",
        steps=[
            PlanStep(id=0, agent="accumulator", task={"value": 10},
                     description="step 0", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="accumulator", task={"value": 5},
                     description="step 1", depends_on=[0], status=StepStatus.APPROVED),
        ],
    )

    results = asyncio.run(dispatcher.execute_plan(plan))
    # Step 1 should have received step 0's result as upstream
    assert results[1].data["value"] == 15  # 5 + 10 from upstream


def test_dag_emits_orchestration_events():
    bus, pool = _make_pool()
    dispatcher = Dispatcher(pool=pool, bus=bus)

    captured = []
    async def capture(event):
        captured.append(event)
    bus.subscribe("orchestration.*", capture)

    plan = Plan(
        id="test-events",
        description="test events",
        steps=[
            PlanStep(id=0, agent="accumulator", task={"value": 1},
                     description="step 0", depends_on=[], status=StepStatus.APPROVED),
        ],
    )

    asyncio.run(dispatcher.execute_plan(plan))
    # Allow event handlers to run
    asyncio.run(asyncio.sleep(0.1))

    event_types = [str(e.type) for e in captured]
    assert "orchestration.step_started" in event_types
    assert "orchestration.step_completed" in event_types


def test_dag_broadcast_event_for_parallel_steps():
    bus, pool = _make_pool()
    dispatcher = Dispatcher(pool=pool, bus=bus)

    captured = []
    async def capture(event):
        captured.append(event)
    bus.subscribe("orchestration.*", capture)

    plan = Plan(
        id="test-broadcast",
        description="test broadcast",
        steps=[
            PlanStep(id=0, agent="accumulator", task={"value": 1},
                     description="a", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="accumulator", task={"value": 2},
                     description="b", depends_on=[], status=StepStatus.APPROVED),
        ],
    )

    asyncio.run(dispatcher.execute_plan(plan))
    asyncio.run(asyncio.sleep(0.1))

    broadcast_events = [e for e in captured if str(e.type) == "orchestration.broadcast"]
    assert len(broadcast_events) >= 1
