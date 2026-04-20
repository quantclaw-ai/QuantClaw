import pytest
import asyncio
from quantclaw.state.db import StateDB
from quantclaw.state.tasks import TaskStore, TaskStatus

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_quantclaw.db"
    return asyncio.run(StateDB.create(str(db_path)))

def test_create_task(db):
    store = TaskStore(db)
    task_id = asyncio.run(store.create(
        agent="validator",
        command="backtest --config gap_1pct",
        status=TaskStatus.PENDING,
    ))
    assert task_id is not None
    task = asyncio.run(store.get(task_id))
    assert task["agent"] == "validator"
    assert task["status"] == "pending"

def test_update_task_status(db):
    store = TaskStore(db)
    task_id = asyncio.run(store.create(agent="miner", command="mine", status=TaskStatus.PENDING))
    asyncio.run(store.update_status(task_id, TaskStatus.RUNNING))
    task = asyncio.run(store.get(task_id))
    assert task["status"] == "running"

def test_list_tasks_by_status(db):
    store = TaskStore(db)
    asyncio.run(store.create(agent="a", command="x", status=TaskStatus.PENDING))
    asyncio.run(store.create(agent="b", command="y", status=TaskStatus.RUNNING))
    pending = asyncio.run(store.list_by_status(TaskStatus.PENDING))
    assert len(pending) == 1
    assert pending[0]["agent"] == "a"
