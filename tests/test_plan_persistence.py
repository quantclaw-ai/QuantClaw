"""Tests for plan and event persistence."""
import asyncio
import pytest
from quantclaw.state.db import StateDB
from quantclaw.state.plans import PlanStore
from quantclaw.state.event_persister import EventPersister
from quantclaw.execution.plan import Plan, PlanStep, PlanStatus, StepStatus
from quantclaw.events.types import Event, EventType


@pytest.fixture
def db(tmp_path):
    async def _create():
        return await StateDB.create(str(tmp_path / "test.db"))
    return asyncio.run(_create())


def test_save_and_load_plan(db):
    store = PlanStore(db)

    async def _run():
        plan = Plan(
            id="test-1", description="test plan",
            steps=[
                PlanStep(id=0, agent="researcher", task={"query": "test"},
                         description="research", depends_on=[]),
            ],
        )
        await store.save(plan)
        loaded = await store.get("test-1")
        assert loaded is not None
        assert loaded.description == "test plan"
        assert len(loaded.steps) == 1
        assert loaded.steps[0].agent == "researcher"

    asyncio.run(_run())


def test_list_plans_by_status(db):
    store = PlanStore(db)

    async def _run():
        plan = Plan(id="p1", description="proposed", steps=[],
                    status=PlanStatus.PROPOSED)
        await store.save(plan)
        plans = await store.list_by_status(PlanStatus.PROPOSED)
        assert len(plans) == 1
        assert plans[0].id == "p1"

    asyncio.run(_run())


def test_update_plan_status(db):
    store = PlanStore(db)

    async def _run():
        plan = Plan(id="p2", description="test", steps=[])
        await store.save(plan)
        await store.update_status("p2", PlanStatus.COMPLETED)
        loaded = await store.get("p2")
        assert loaded.status == PlanStatus.COMPLETED

    asyncio.run(_run())


def test_event_persister_batches(db):
    persister = EventPersister(db, flush_interval=0.1)

    async def _run():
        await persister.handle_event(Event(
            type=EventType.AGENT_TASK_STARTED,
            payload={"agent": "test"},
            source_agent="test",
        ))
        await persister.handle_event(Event(
            type=EventType.AGENT_TASK_COMPLETED,
            payload={"agent": "test"},
            source_agent="test",
        ))

        cursor = await db.conn.execute("SELECT COUNT(*) FROM events")
        count = (await cursor.fetchone())[0]
        assert count == 0

        await persister.flush()

        cursor = await db.conn.execute("SELECT COUNT(*) FROM events")
        count = (await cursor.fetchone())[0]
        assert count == 2

    asyncio.run(_run())
