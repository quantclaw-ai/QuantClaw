"""Tests for plan cancellation."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.execution.dispatcher import Dispatcher
from quantclaw.execution.pool import AgentPool
from quantclaw.execution.plan import Plan, PlanStep, StepStatus


class SlowAgent(BaseAgent):
    name = "slow"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        await asyncio.sleep(5)
        return AgentResult(status=AgentStatus.SUCCESS, data={"done": True})


def test_cancel_stops_plan():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("slow", SlowAgent)
    cancel = asyncio.Event()
    dispatcher = Dispatcher(pool=pool, bus=bus, cancel_event=cancel)

    plan = Plan(
        id="cancel-test",
        description="test cancellation",
        steps=[
            PlanStep(id=0, agent="slow", task={}, description="step 0",
                     depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="slow", task={}, description="step 1",
                     depends_on=[0], status=StepStatus.APPROVED),
        ],
    )

    async def _run():
        async def cancel_soon():
            await asyncio.sleep(0.1)
            cancel.set()
        asyncio.create_task(cancel_soon())

        results = await dispatcher.execute_plan(plan)
        cancelled_or_skipped = sum(
            1 for s in plan.steps
            if s.status in (StepStatus.FAILED, StepStatus.SKIPPED)
        )
        assert cancelled_or_skipped >= 1

    asyncio.run(_run())


def test_no_cancel_event_works_normally():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})

    class FastAgent(BaseAgent):
        name = "fast"
        model = "sonnet"
        async def execute(self, task: dict) -> AgentResult:
            return AgentResult(status=AgentStatus.SUCCESS, data={"ok": True})

    pool.register("fast", FastAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)

    plan = Plan(
        id="no-cancel",
        description="normal",
        steps=[
            PlanStep(id=0, agent="fast", task={}, description="step 0",
                     depends_on=[], status=StepStatus.APPROVED),
        ],
    )

    results = asyncio.run(dispatcher.execute_plan(plan))
    assert results[0].status == AgentStatus.SUCCESS
