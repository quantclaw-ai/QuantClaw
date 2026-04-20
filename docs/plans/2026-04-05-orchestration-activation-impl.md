# Orchestration Engine Activation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Activate the orchestration engine so the OODA loop runs continuously, chat routes through the Scheduler, all state persists across restarts, and agents can search the web.

**Architecture:** The OODA loop runs as a background asyncio.Task inside FastAPI's lifespan. Chat messages feed into it as CEO intent. State persists to Playbook (JSONL) and SQLite. Agents share a web_search tool. A cancellation token enables stop-button and cancel-and-replace.

**Tech Stack:** Python 3.12+ (FastAPI, asyncio, aiosqlite), TypeScript (Next.js React hooks), Ollama/Anthropic/OpenAI

---

## Task 1: New Event Types + Config

Add the two new event types and the orchestration config section.

**Files:**
- Modify: `quantclaw/events/types.py`
- Modify: `quantclaw/config/default.yaml`

**Step 1: Add event types to `quantclaw/events/types.py`**

Add after the existing orchestration events:

```python
    CHAT_NARRATIVE = "chat.narrative"
    ORCHESTRATION_CYCLE_COMPLETE = "orchestration.cycle_complete"
```

**Step 2: Add orchestration + search config to `quantclaw/config/default.yaml`**

Add at the end of the file:

```yaml
orchestration:
  max_cycles_per_goal: 3
  cycle_timeout_minutes: 20
  ooda_interval: 30
  max_chat_history: 10
  max_debugger_retries: 5
  loop_similarity_threshold: 0.85

search:
  provider: duckduckgo
  api_key: "${SEARCH_API_KEY}"
```

**Step 3: Add Ollama provider to config**

Add to the existing `providers:` section:

```yaml
  local:
    provider: ollama
    model: llama3.1
```

**Step 4: Run existing tests**

Run: `python -m pytest tests/test_events.py tests/test_config.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add quantclaw/events/types.py quantclaw/config/default.yaml
git commit -m "feat: add chat narrative, cycle complete events and orchestration config"
```

---

## Task 2: Ollama Support in LLMRouter

**Files:**
- Modify: `quantclaw/orchestrator/router.py`
- Create: `tests/test_ollama_router.py`

**Step 1: Write the failing test**

```python
# tests/test_ollama_router.py
"""Tests for Ollama provider in LLMRouter."""
from quantclaw.orchestrator.router import LLMRouter


def test_ollama_provider_config():
    config = {
        "models": {"scheduler": "local"},
        "providers": {"local": {"provider": "ollama", "model": "llama3.1"}},
    }
    router = LLMRouter(config)
    provider = router.get_provider("scheduler")
    assert provider["provider"] == "ollama"
    assert provider["model"] == "llama3.1"


def test_ollama_url_default():
    config = {"models": {}, "providers": {}}
    router = LLMRouter(config)
    assert router.get_ollama_url() == "http://localhost:11434"


def test_ollama_url_from_config():
    config = {"models": {}, "providers": {}, "ollama_url": "http://custom:11434"}
    router = LLMRouter(config)
    assert router.get_ollama_url() == "http://custom:11434"
```

**Step 2: Add Ollama support to `quantclaw/orchestrator/router.py`**

Add method to LLMRouter:

```python
def get_ollama_url(self) -> str:
    return self._config.get("ollama_url", "http://localhost:11434")
```

Add to `call()` method, before the raise at the end:

```python
    elif provider["provider"] == "ollama":
        return await self._call_ollama(provider["model"], messages, system, temp)
```

Add the `_call_ollama` method:

```python
async def _call_ollama(self, model: str, messages: list[dict],
                       system: str = None, temperature: float = 0.5) -> str:
    import httpx
    ollama_url = self.get_ollama_url()
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{ollama_url}/api/chat",
            json={"model": model, "messages": msgs, "stream": False,
                  "options": {"temperature": temperature}},
        )
        data = resp.json()
        return data.get("message", {}).get("content", "")
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_ollama_router.py tests/test_router.py tests/test_temperature.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/orchestrator/router.py tests/test_ollama_router.py
git commit -m "feat: add Ollama provider support to LLMRouter"
```

---

## Task 3: Cancellable Dispatcher

Add a cancellation token to the Dispatcher so running plans can be stopped.

**Files:**
- Modify: `quantclaw/orchestrator/dispatcher.py`
- Create: `tests/test_cancellation.py`

**Step 1: Write the failing test**

```python
# tests/test_cancellation.py
"""Tests for plan cancellation."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool
from quantclaw.orchestrator.plan import Plan, PlanStep, StepStatus


class SlowAgent(BaseAgent):
    name = "slow"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        await asyncio.sleep(5)  # Simulate slow work
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
        # Cancel after a short delay
        async def cancel_soon():
            await asyncio.sleep(0.1)
            cancel.set()
        asyncio.create_task(cancel_soon())

        results = await dispatcher.execute_plan(plan)
        # Step 0 should be cancelled/failed, step 1 should never start
        cancelled_or_failed = sum(
            1 for s in plan.steps
            if s.status in (StepStatus.FAILED, StepStatus.SKIPPED)
        )
        assert cancelled_or_failed >= 1

    asyncio.run(_run())


def test_no_cancel_event_works_normally():
    """Dispatcher without cancel_event works as before."""
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
```

**Step 2: Update Dispatcher**

In `quantclaw/orchestrator/dispatcher.py`, update `__init__`:

```python
def __init__(self, pool: AgentPool, bus: EventBus | None = None,
             cancel_event: asyncio.Event | None = None):
    self._pool = pool
    self._bus = bus
    self._cancel = cancel_event
```

Add `import asyncio` at the top if not already present.

In `execute_plan`, add cancellation check at the start of the while loop and in `run_step`:

```python
async def execute_plan(self, plan: Plan) -> dict[int, AgentResult]:
    results: dict[int, AgentResult] = {}

    while not plan.is_complete():
        # Check cancellation
        if self._cancel and self._cancel.is_set():
            for step in plan.steps:
                if step.status in (StepStatus.APPROVED, StepStatus.PENDING):
                    step.status = StepStatus.SKIPPED
            break

        ready = plan.get_ready_steps()
        if not ready:
            break

        # ... existing broadcast logic ...

        async def run_step(step: PlanStep) -> tuple[int, AgentResult]:
            if self._cancel and self._cancel.is_set():
                step.status = StepStatus.SKIPPED
                return step.id, AgentResult(status=AgentStatus.FAILED, error="Cancelled")

            # ... existing upstream injection + emit + dispatch ...
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_cancellation.py tests/test_orchestrator.py tests/test_dag_execution.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/orchestrator/dispatcher.py tests/test_cancellation.py
git commit -m "feat: add cancellation token to Dispatcher for stop button"
```

---

## Task 4: Plans Table + Event Batch Persistence

Add the plans table to SQLite schema and implement batched event persistence.

**Files:**
- Modify: `quantclaw/state/db.py`
- Create: `quantclaw/state/plans.py`
- Create: `quantclaw/state/event_persister.py`
- Create: `tests/test_plan_persistence.py`

**Step 1: Add plans table to schema in `quantclaw/state/db.py`**

Add to the SCHEMA string:

```sql
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Step 2: Create `quantclaw/state/plans.py`**

```python
"""Plan persistence: save and restore plans from SQLite."""
from __future__ import annotations
import json
from quantclaw.state.db import StateDB
from quantclaw.orchestrator.plan import Plan, PlanStep, PlanStatus, StepStatus


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
```

**Step 3: Create `quantclaw/state/event_persister.py`**

```python
"""Batched event persistence to SQLite."""
from __future__ import annotations
import asyncio
import json
from quantclaw.events.types import Event
from quantclaw.state.db import StateDB


class EventPersister:
    """Buffers events and flushes to SQLite every flush_interval seconds."""

    def __init__(self, db: StateDB, flush_interval: float = 5.0):
        self._db = db
        self._flush_interval = flush_interval
        self._buffer: list[Event] = []
        self._task: asyncio.Task | None = None

    async def handle_event(self, event: Event) -> None:
        self._buffer.append(event)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    async def flush(self) -> None:
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        for event in batch:
            await self._db.conn.execute(
                "INSERT INTO events (event_type, payload, source_agent) VALUES (?, ?, ?)",
                (str(event.type), json.dumps(event.payload), event.source_agent),
            )
        await self._db.conn.commit()

    def start(self) -> None:
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush()  # Final flush
```

**Step 4: Write tests**

```python
# tests/test_plan_persistence.py
"""Tests for plan and event persistence."""
import asyncio
import pytest
from quantclaw.state.db import StateDB
from quantclaw.state.plans import PlanStore
from quantclaw.state.event_persister import EventPersister
from quantclaw.orchestrator.plan import Plan, PlanStep, PlanStatus, StepStatus
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

        # Not flushed yet
        cursor = await db.conn.execute("SELECT COUNT(*) FROM events")
        count = (await cursor.fetchone())[0]
        assert count == 0

        # Manual flush
        await persister.flush()

        cursor = await db.conn.execute("SELECT COUNT(*) FROM events")
        count = (await cursor.fetchone())[0]
        assert count == 2

    asyncio.run(_run())
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_plan_persistence.py -v`
Expected: All 4 PASS

**Step 6: Commit**

```bash
git add quantclaw/state/db.py quantclaw/state/plans.py quantclaw/state/event_persister.py tests/test_plan_persistence.py
git commit -m "feat: add plan persistence and batched event persistence"
```

---

## Task 5: Autonomy + Goal Persistence

Make autonomy mode and goal persist to playbook so they survive restarts.

**Files:**
- Modify: `quantclaw/orchestration/autonomy.py`
- Modify: `quantclaw/orchestration/ooda.py`
- Create: `tests/test_persistence.py`

**Step 1: Write the failing tests**

```python
# tests/test_persistence.py
"""Tests for goal and autonomy mode persistence."""
import asyncio
import pytest
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.playbook import Playbook, EntryType


def test_autonomy_mode_persists(tmp_path):
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    am = AutonomyManager(playbook=pb)

    async def _run():
        await am.set_mode_persistent(AutonomyMode.AUTOPILOT)
        assert am.mode == AutonomyMode.AUTOPILOT

        # Restore from playbook
        am2 = await AutonomyManager.from_playbook(pb)
        assert am2.mode == AutonomyMode.AUTOPILOT

    asyncio.run(_run())


def test_goal_persists(tmp_path):
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        # Save goal
        await pb.add(EntryType.CEO_PREFERENCE, {"goal": "find momentum"})

        # Restore
        entries = await pb.query(entry_type=EntryType.CEO_PREFERENCE)
        goals = [e for e in entries if "goal" in e.content]
        assert len(goals) == 1
        assert goals[-1].content["goal"] == "find momentum"

    asyncio.run(_run())


def test_autonomy_default_without_playbook():
    am = AutonomyManager()
    assert am.mode == AutonomyMode.PLAN
```

**Step 2: Update `quantclaw/orchestration/autonomy.py`**

Add playbook support:

```python
class AutonomyManager:
    def __init__(self, initial_mode: AutonomyMode = AutonomyMode.PLAN,
                 playbook: Playbook | None = None):
        self._mode = initial_mode
        self._playbook = playbook
        self._mode_history: list[tuple[AutonomyMode, str]] = [
            (initial_mode, datetime.now(timezone.utc).isoformat())
        ]

    # Keep existing set_mode() for non-persistent changes

    async def set_mode_persistent(self, mode: AutonomyMode) -> None:
        """Set mode and persist to playbook."""
        self.set_mode(mode)
        if self._playbook:
            from quantclaw.orchestration.playbook import EntryType
            await self._playbook.add(EntryType.CEO_PREFERENCE, {
                "autonomy_mode": mode.value,
            })

    @classmethod
    async def from_playbook(cls, playbook: Playbook) -> AutonomyManager:
        """Restore autonomy mode from playbook."""
        from quantclaw.orchestration.playbook import EntryType
        entries = await playbook.query(entry_type=EntryType.CEO_PREFERENCE)
        mode = AutonomyMode.PLAN
        for entry in reversed(entries):
            if "autonomy_mode" in entry.content:
                try:
                    mode = AutonomyMode(entry.content["autonomy_mode"])
                except ValueError:
                    pass
                break
        return cls(initial_mode=mode, playbook=playbook)
```

Add TYPE_CHECKING import for Playbook at the top:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from quantclaw.orchestration.playbook import Playbook
```

**Step 3: Update `quantclaw/orchestration/ooda.py` — add persistent goal**

Add a `set_goal_persistent` method:

```python
async def set_goal_persistent(self, goal: str) -> None:
    """Set goal and persist to playbook."""
    self._goal = goal
    self._wake_event.set()
    await self._playbook.add(EntryType.CEO_PREFERENCE, {"goal": goal})
```

Add a `restore_goal` classmethod or static method:

```python
@staticmethod
async def restore_goal(playbook: Playbook) -> str:
    """Restore goal from playbook."""
    entries = await playbook.query(entry_type=EntryType.CEO_PREFERENCE)
    for entry in reversed(entries):
        if "goal" in entry.content:
            return entry.content["goal"]
    return ""
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_persistence.py tests/test_autonomy.py tests/test_ooda.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add quantclaw/orchestration/autonomy.py quantclaw/orchestration/ooda.py tests/test_persistence.py
git commit -m "feat: persist autonomy mode and goal to playbook"
```

---

## Task 6: Web Search Tool

Create the shared web search tool with DuckDuckGo as the free default.

**Files:**
- Create: `quantclaw/agents/tools/web_search.py`
- Create: `tests/test_web_search.py`

**Step 1: Write the failing test**

```python
# tests/test_web_search.py
"""Tests for shared web search tool."""
import asyncio
import pytest
from quantclaw.agents.tools.web_search import web_search, get_search_provider


def test_get_default_provider():
    config = {}
    provider = get_search_provider(config)
    assert provider == "duckduckgo"


def test_get_configured_provider():
    config = {"search": {"provider": "brave"}}
    provider = get_search_provider(config)
    assert provider == "brave"


def test_search_policy_allowed():
    from quantclaw.agents.tools.web_search import is_search_allowed
    assert is_search_allowed("researcher")
    assert is_search_allowed("miner")
    assert is_search_allowed("scheduler")
    assert not is_search_allowed("executor")
    assert not is_search_allowed("compliance")
```

**Step 2: Create `quantclaw/agents/tools/web_search.py`**

```python
"""Shared web search tool — available to any agent via policy."""
from __future__ import annotations
from typing import Any

# Agents allowed to use web search
SEARCH_ALLOWED_AGENTS = frozenset({
    "researcher", "miner", "scheduler", "ingestor",
    "trainer", "reporter", "debugger", "sentinel",
})


def is_search_allowed(agent_name: str) -> bool:
    return agent_name in SEARCH_ALLOWED_AGENTS


def get_search_provider(config: dict) -> str:
    return config.get("search", {}).get("provider", "duckduckgo")


async def web_search(
    query: str,
    config: dict | None = None,
    max_results: int = 5,
) -> list[dict[str, str]]:
    """Search the web using the configured provider.

    Returns list of {title, url, snippet} dicts.
    """
    provider = get_search_provider(config or {})

    if provider == "duckduckgo":
        return await _search_duckduckgo(query, max_results)
    elif provider == "brave":
        api_key = (config or {}).get("search", {}).get("api_key", "")
        return await _search_brave(query, api_key, max_results)
    elif provider == "tavily":
        api_key = (config or {}).get("search", {}).get("api_key", "")
        return await _search_tavily(query, api_key, max_results)
    else:
        return await _search_duckduckgo(query, max_results)


async def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search via DuckDuckGo HTML (no API key needed)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "QuantClaw/0.1"},
            )
            # Parse basic results from HTML
            results = []
            text = resp.text
            # Simple extraction — find result links
            import re
            links = re.findall(
                r'<a rel="nofollow" class="result__a" href="([^"]+)">(.+?)</a>',
                text
            )
            snippets = re.findall(
                r'<a class="result__snippet"[^>]*>(.+?)</a>',
                text
            )
            for i, (url, title) in enumerate(links[:max_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                # Clean HTML tags from title and snippet
                title = re.sub(r'<[^>]+>', '', title).strip()
                snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                results.append({"title": title, "url": url, "snippet": snippet})
            return results
    except Exception:
        return []


async def _search_brave(query: str, api_key: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search via Brave Search API."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            )
            data = resp.json()
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("description", "")}
                for r in data.get("web", {}).get("results", [])[:max_results]
            ]
    except Exception:
        return []


async def _search_tavily(query: str, api_key: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search via Tavily API."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"query": query, "max_results": max_results, "api_key": api_key},
            )
            data = resp.json()
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("content", "")}
                for r in data.get("results", [])[:max_results]
            ]
    except Exception:
        return []
```

Ensure `quantclaw/agents/tools/__init__.py` exists (may already exist).

**Step 3: Run tests**

Run: `python -m pytest tests/test_web_search.py -v`
Expected: All 3 PASS

**Step 4: Commit**

```bash
git add quantclaw/agents/tools/web_search.py tests/test_web_search.py
git commit -m "feat: add shared web_search tool with DuckDuckGo/Brave/Tavily providers"
```

---

## Task 7: OODA Loop — run_cycle + run_continuous + Narrative

This is the core activation task. Add `run_cycle()` for chat-triggered execution, `run_continuous()` for background operation, narrative generation, cycle limits, and debugger escalation.

**Files:**
- Modify: `quantclaw/orchestration/ooda.py`
- Create: `tests/test_ooda_activation.py`

**Step 1: Write the failing tests**

```python
# tests/test_ooda_activation.py
"""Tests for OODA activation: run_cycle, run_continuous, narrative, cycle limits."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool


class StubAgent(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "found data"})


def _make(tmp_path, mode=AutonomyMode.AUTOPILOT):
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=mode),
                    dispatcher=dispatcher, config={})
    return bus, pb, ooda


def test_run_cycle_completes(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    narratives = []
    async def capture(event):
        if str(event.type) == "chat.narrative":
            narratives.append(event.payload.get("message", ""))

    bus.subscribe("chat.*", capture)

    async def _run():
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        assert ooda.phase == OODAPhase.SLEEP

    asyncio.run(_run())


def test_run_cycle_emits_cycle_complete(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    events = []
    async def capture(event):
        events.append(str(event.type))

    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        await asyncio.sleep(0.1)

    asyncio.run(_run())
    assert "orchestration.cycle_complete" in events


def test_cycle_count_tracking(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    async def _run():
        ooda.set_goal("test goal")
        assert ooda.cycle_count == 0
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        assert ooda.cycle_count == 1

    asyncio.run(_run())
```

**Step 2: Update `quantclaw/orchestration/ooda.py`**

Add these attributes to `__init__`:

```python
self._cycle_count = 0
self._plan_history: list[str] = []  # For loop detection
```

Add property:

```python
@property
def cycle_count(self) -> int:
    return self._cycle_count
```

Add `run_cycle` method:

```python
async def run_cycle(self, chat_history: list[dict] | None = None) -> dict | None:
    """Run a single OODA cycle: observe → orient → decide → act → learn → sleep.

    Returns the plan execution results, or None if no action needed.
    """
    # Observe
    state = await self.observe()
    if chat_history:
        state["chat_history"] = chat_history[-self._config.get(
            "orchestration", {}).get("max_chat_history", 10):]

    # Orient
    orientation = await self.orient(state)

    # Decide
    plan = await self.decide(orientation)
    if plan is None:
        await self.sleep()
        return None

    # Act
    results = await self.act(plan)
    self._cycle_count += 1

    # Learn from results
    for step_id, result in results.items():
        if result.status == AgentStatus.SUCCESS and result.data:
            await self.learn({
                "type": "strategy_result",
                "content": result.data,
                "tags": ["auto"],
            })

    # Emit cycle complete
    await self._bus.publish(Event(
        type=EventType.ORCHESTRATION_CYCLE_COMPLETE,
        payload={"cycle": self._cycle_count, "plan_id": plan.id,
                 "steps_completed": len([r for r in results.values()
                                         if r.status == AgentStatus.SUCCESS])},
        source_agent="scheduler",
    ))

    await self.sleep()
    return results
```

Add `run_continuous` method:

```python
async def run_continuous(self) -> None:
    """Run OODA loop continuously as a background task."""
    max_cycles = self._config.get("orchestration", {}).get("max_cycles_per_goal", 3)
    timeout_minutes = self._config.get("orchestration", {}).get("cycle_timeout_minutes", 20)
    interval = self._config.get("orchestration", {}).get("ooda_interval", 30)

    while True:
        # Wait for trigger
        await self.sleep_until_trigger(timeout=interval)

        # Run one cycle with timeout
        try:
            await asyncio.wait_for(
                self.run_cycle(),
                timeout=timeout_minutes * 60,
            )
        except asyncio.TimeoutError:
            await self._bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={"message": f"Cycle timed out after {timeout_minutes} minutes.",
                         "role": "scheduler"},
                source_agent="scheduler",
            ))

        # Check cycle limit for autopilot
        if (self._autonomy.mode == AutonomyMode.AUTOPILOT
                and self._goal
                and self._cycle_count >= max_cycles):
            await self._bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={"message": f"Completed {max_cycles} cycles. Here's what I've found so far. Want me to keep exploring?",
                         "role": "scheduler"},
                source_agent="scheduler",
            ))
            self._cycle_count = 0  # Reset for next batch
            # Wait for CEO response (goes back to sleep_until_trigger)
```

Add the `AgentStatus` import at the top:

```python
from quantclaw.agents.base import AgentStatus
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_ooda_activation.py tests/test_ooda.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/orchestration/ooda.py tests/test_ooda_activation.py
git commit -m "feat: add run_cycle, run_continuous, cycle tracking to OODA loop"
```

---

## Task 8: Activate OODA in FastAPI Lifespan

Move all orchestration objects into the FastAPI lifespan and start the OODA background task.

**Files:**
- Modify: `quantclaw/dashboard/api.py`

**Step 1: Read current api.py to understand the lifespan and module-level objects**

**Step 2: Update the lifespan function**

Replace the existing lifespan with the orchestration-aware version:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db, _config
    _config = load_config()
    _db = await StateDB.create("data/quantclaw.db")
    _pm.discover()

    # ── Orchestration setup ──
    from quantclaw.orchestration.playbook import Playbook
    from quantclaw.orchestration.trust import TrustManager
    from quantclaw.orchestration.autonomy import AutonomyManager
    from quantclaw.orchestration.ooda import OODALoop
    from quantclaw.orchestrator.dispatcher import Dispatcher
    from quantclaw.orchestrator.pool import AgentPool
    from quantclaw.orchestrator.router import LLMRouter
    from quantclaw.state.event_persister import EventPersister
    from quantclaw.state.plans import PlanStore
    from quantclaw.state.tasks import TaskStore
    from quantclaw.agents import ALL_AGENTS

    playbook = Playbook("data/playbook.jsonl")
    trust = await TrustManager.from_playbook(playbook, bus=_bus)
    autonomy = await AutonomyManager.from_playbook(playbook)

    pool = AgentPool(bus=_bus, config=_config)
    for name, agent_cls in ALL_AGENTS.items():
        pool.register(name, agent_cls)

    cancel_event = asyncio.Event()
    dispatcher = Dispatcher(pool=pool, bus=_bus, cancel_event=cancel_event)

    ooda = OODALoop(
        bus=_bus, playbook=playbook, trust=trust, autonomy=autonomy,
        dispatcher=dispatcher, config=_config,
    )

    # Restore goal
    goal = await OODALoop.restore_goal(playbook)
    if goal:
        ooda.set_goal(goal)

    # Restore pending tasks
    task_store = TaskStore(_db)
    from quantclaw.state.tasks import TaskStatus
    import json as _json
    pending = await task_store.list_by_status(TaskStatus.PENDING)
    for task in pending:
        try:
            task_data = _json.loads(task["command"])
            ooda.add_pending_task(task_data)
        except (ValueError, KeyError):
            pass

    # Event persistence
    persister = EventPersister(_db)
    _bus.subscribe("*", persister.handle_event)
    persister.start()

    # Store on app.state
    app.state.ooda = ooda
    app.state.trust = trust
    app.state.autonomy = autonomy
    app.state.playbook = playbook
    app.state.dispatcher = dispatcher
    app.state.cancel_event = cancel_event
    app.state.task_store = task_store
    app.state.plan_store = PlanStore(_db)
    app.state.persister = persister

    # Start OODA background task
    async def _ooda_background():
        while True:
            try:
                await ooda.run_continuous()
            except asyncio.CancelledError:
                break
            except Exception as e:
                await _bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={"message": f"Scheduler restarting after error: {e}",
                             "role": "scheduler"},
                    source_agent="scheduler",
                ))
                await asyncio.sleep(5)

    ooda_task = asyncio.create_task(_ooda_background())
    app.state.ooda_task = ooda_task

    yield

    # Shutdown
    ooda_task.cancel()
    try:
        await ooda_task
    except asyncio.CancelledError:
        pass
    await persister.stop()
    if _db:
        await _db.close()
```

**Step 3: Remove module-level orchestration objects**

Remove the module-level `_playbook`, `_trust`, `_autonomy`, `_orc_pool`, `_orc_dispatcher`, `_ooda` that were added in Task 9 of the previous implementation. These are now in the lifespan.

**Step 4: Update orchestration endpoints to use `request.app.state`**

All `/api/orchestration/*` endpoints need to change from module-level references to `request.app.state`. Since FastAPI sync endpoints don't have `request` by default with `body: dict`, we need to add `Request` parameter:

```python
from fastapi import Request

@app.get("/api/orchestration/status")
def orchestration_status(request: Request):
    ooda = request.app.state.ooda
    autonomy = request.app.state.autonomy
    trust = request.app.state.trust
    return {
        "autonomy_mode": autonomy.mode.value,
        "trust_level": trust.level.name,
        "trust_level_id": int(trust.level),
        "ooda_phase": ooda.phase.value,
        "trust_metrics": trust.get_metrics(),
    }
```

Do the same for all other orchestration endpoints (`/api/orchestration/mode`, `/api/orchestration/playbook/recent`, `/api/orchestration/trust`, `/api/orchestration/trust/upgrade`, `/api/orchestration/kill`, `/api/orchestration/goal`).

**Step 5: Add stop endpoint**

```python
@app.post("/api/orchestration/stop")
async def stop_workflow(request: Request):
    """Stop button — cancel current workflow."""
    cancel = request.app.state.cancel_event
    cancel.set()
    autonomy = request.app.state.autonomy
    autonomy.set_mode(AutonomyMode.PLAN)
    await _bus.publish(Event(
        type=EventType.CHAT_NARRATIVE,
        payload={"message": "Workflow stopped.", "role": "scheduler"},
        source_agent="scheduler",
    ))
    # Reset cancel event for next workflow
    cancel.clear()
    return {"status": "stopped"}
```

**Step 6: Run tests**

Run: `python -m pytest tests/test_orchestration_api.py tests/test_dashboard_api.py -v`
Expected: All PASS (update test imports if needed to account for app.state)

**Step 7: Commit**

```bash
git add quantclaw/dashboard/api.py
git commit -m "feat: activate OODA loop in FastAPI lifespan with full state management"
```

---

## Task 9: Route Chat Through OODA

Modify `/api/chat` to route non-@agent messages through the orchestration engine.

**Files:**
- Modify: `quantclaw/dashboard/api.py`

**Step 1: Update the `/api/chat` endpoint**

At the beginning of the chat function, before provider routing, add the orchestration path:

```python
@app.post("/api/chat")
async def chat(body: dict, request: Request):
    message = body.get("message", "")
    history = body.get("history", [])
    provider = body.get("provider", "ollama")
    explicit_agent = body.get("agent", "")

    if not message:
        return {"error": "message is required"}

    # Check for @agent prefix — direct chat bypasses orchestration
    if explicit_agent and explicit_agent in AGENT_SYSTEM_PROMPTS:
        # Existing direct agent chat flow (unchanged)
        # ... all existing provider handling code ...
        pass
    else:
        # ── Orchestration path: CEO intent → OODA loop ──
        ooda = request.app.state.ooda
        cancel = request.app.state.cancel_event

        # Cancel-and-replace if mid-cycle
        if ooda.phase not in ("sleep",):
            cancel.set()
            await asyncio.sleep(0.2)  # Brief pause for cancellation
            cancel.clear()
            await _bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={"message": "Understood — switching to your new request...",
                         "role": "scheduler"},
                source_agent="scheduler",
            ))

        # Set goal and trigger cycle
        await ooda.set_goal_persistent(message)
        chat_history = history[-10:] if history else []

        # Run cycle in background
        async def _run_cycle():
            try:
                await ooda.run_cycle(chat_history=chat_history)
            except Exception as e:
                await _bus.publish(Event(
                    type=EventType.CHAT_NARRATIVE,
                    payload={"message": f"Error: {e}", "role": "scheduler"},
                    source_agent="scheduler",
                ))

        asyncio.create_task(_run_cycle())

        await emit_floor_event("agent.task.started", agent="scheduler",
                               message=f"Planning: {message[:50]}...")

        return {"status": "orchestrating", "agent": "scheduler"}
```

The key: the existing provider-specific code (Ollama, OpenAI, Anthropic, Google, etc.) only runs for `@agent` direct chat. Non-prefixed messages go through the OODA loop.

**Step 2: Run tests**

Run: `python -m pytest tests/test_dashboard_api.py tests/test_orchestration_api.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add quantclaw/dashboard/api.py
git commit -m "feat: route chat through OODA loop for orchestrated execution"
```

---

## Task 10: Frontend — Chat Stream Hook + Stop Button

Add the `useChatStream` hook and handle new event types in `useFloorEvents`.

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts`
- Create: `quantclaw/dashboard/app/app/dashboard/chat/useChatStream.ts`

**Step 1: Add new event cases to `useFloorEvents.ts`**

Add to the switch statement:

```typescript
case "chat.narrative": {
  // Scheduler is speaking — show on scheduler station
  const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
  if (schedulerIdx >= 0) {
    const msg = (event.payload?.message as string) || event.message || "";
    updated[schedulerIdx] = {
      ...updated[schedulerIdx],
      speechBubble: msg.slice(0, 80),
    };
  }
  break;
}

case "orchestration.cycle_complete": {
  // Reset scheduler to idle
  const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
  if (schedulerIdx >= 0) {
    updated[schedulerIdx] = {
      ...updated[schedulerIdx],
      state: "idle",
      progress: 0,
      speechBubble: "Cycle complete",
    };
    setTimeout(() => {
      setAgents((prev2) => {
        const u = [...prev2];
        const i = u.findIndex((a) => a.name === "scheduler");
        if (i >= 0) {
          u[i] = { ...u[i], speechBubble: null };
        }
        return u;
      });
    }, 5000);
  }
  break;
}
```

**Step 2: Create `useChatStream.ts`**

```typescript
"use client";
import { useEffect, useCallback, useRef } from "react";

const WS_URL = "ws://localhost:8000/ws/events";

export interface ChatNarrative {
  message: string;
  role: string;
  timestamp?: string;
}

/**
 * Hook that subscribes to WebSocket for chat.narrative events.
 * Returns a callback to register a message handler.
 */
export function useChatStream(
  onNarrative: (narrative: ChatNarrative) => void,
  onCycleComplete: () => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const onNarrativeRef = useRef(onNarrative);
  const onCycleCompleteRef = useRef(onCycleComplete);

  // Keep refs updated
  useEffect(() => {
    onNarrativeRef.current = onNarrative;
    onCycleCompleteRef.current = onCycleComplete;
  }, [onNarrative, onCycleComplete]);

  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data);

            if (event.type === "chat.narrative") {
              onNarrativeRef.current({
                message: event.payload?.message || "",
                role: event.payload?.role || "scheduler",
                timestamp: event.timestamp,
              });
            }

            if (event.type === "orchestration.cycle_complete") {
              onCycleCompleteRef.current();
            }
          } catch {}
        };

        ws.onclose = () => {
          wsRef.current = null;
          setTimeout(connect, 2000);
        };
      } catch {
        setTimeout(connect, 2000);
      }
    }

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);
}
```

Ensure the directory exists: `quantclaw/dashboard/app/app/dashboard/chat/`

**Step 3: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts quantclaw/dashboard/app/app/dashboard/chat/useChatStream.ts
git commit -m "feat: add chat stream hook and frontend orchestration event handling"
```

---

## Task 11: Integration Test — Full Activation

End-to-end test that exercises: chat → OODA → agents → narrative → cycle complete.

**Files:**
- Create: `tests/test_activation_integration.py`

**Step 1: Write the integration test**

```python
# tests/test_activation_integration.py
"""Integration test: full orchestration activation flow."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool


class MockResearcher(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "findings": "Momentum factor looks promising"
        })


def test_chat_to_ooda_to_results(tmp_path):
    """Simulate: CEO sends message → OODA cycle → agents execute → results."""
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", MockResearcher)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT),
                    dispatcher=dispatcher, config={})

    narratives = []
    cycle_completed = []

    async def capture_narrative(event):
        if str(event.type) == "chat.narrative":
            narratives.append(event.payload.get("message", ""))

    async def capture_cycle(event):
        if str(event.type) == "orchestration.cycle_complete":
            cycle_completed.append(True)

    bus.subscribe("chat.*", capture_narrative)
    bus.subscribe("orchestration.*", capture_cycle)

    async def _run():
        # CEO sends message
        ooda.set_goal("find momentum strategies")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "momentum"}})

        # Run one cycle
        results = await ooda.run_cycle(chat_history=[
            {"role": "user", "content": "find momentum strategies"}
        ])

        await asyncio.sleep(0.1)  # Let events propagate

        assert results is not None
        assert ooda.phase == OODAPhase.SLEEP
        assert ooda.cycle_count == 1
        assert len(cycle_completed) >= 1

    asyncio.run(_run())


def test_cancel_and_replace(tmp_path):
    """Simulate: CEO sends message, then sends another mid-cycle."""
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})

    class SlowAgent(BaseAgent):
        name = "researcher"
        model = "sonnet"
        async def execute(self, task: dict) -> AgentResult:
            await asyncio.sleep(2)
            return AgentResult(status=AgentStatus.SUCCESS, data={"slow": True})

    pool.register("researcher", SlowAgent)
    cancel = asyncio.Event()
    dispatcher = Dispatcher(pool=pool, bus=bus, cancel_event=cancel)
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT),
                    dispatcher=dispatcher, config={})

    async def _run():
        ooda.set_goal("first task")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "slow"}})

        # Start cycle in background
        cycle_task = asyncio.create_task(ooda.run_cycle())

        # Cancel after brief delay
        await asyncio.sleep(0.1)
        cancel.set()
        await asyncio.sleep(0.1)

        # Cycle should finish (cancelled)
        try:
            await asyncio.wait_for(cycle_task, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        cancel.clear()

    asyncio.run(_run())


def test_state_persists_across_restart(tmp_path):
    """Simulate: set goal + mode, then restore from playbook."""
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        # Session 1: set state
        bus1 = EventBus()
        pool1 = AgentPool(bus=bus1, config={})
        dispatcher1 = Dispatcher(pool=pool1, bus=bus1)
        autonomy1 = AutonomyManager(playbook=pb)
        ooda1 = OODALoop(bus=bus1, playbook=pb, trust=TrustManager(),
                         autonomy=autonomy1, dispatcher=dispatcher1, config={})

        await ooda1.set_goal_persistent("find alpha")
        await autonomy1.set_mode_persistent(AutonomyMode.AUTOPILOT)

        # Session 2: restore
        bus2 = EventBus()
        pool2 = AgentPool(bus=bus2, config={})
        dispatcher2 = Dispatcher(pool=pool2, bus=bus2)
        autonomy2 = await AutonomyManager.from_playbook(pb)
        goal = await OODALoop.restore_goal(pb)

        assert autonomy2.mode == AutonomyMode.AUTOPILOT
        assert goal == "find alpha"

    asyncio.run(_run())
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_activation_integration.py -v`
Expected: All 3 PASS

**Step 3: Commit**

```bash
git add tests/test_activation_integration.py
git commit -m "test: add orchestration activation integration tests"
```

---

## Task 12: Final Verification

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

**Step 2: Verify imports**

Run: `python -c "from quantclaw.orchestration.ooda import OODALoop; from quantclaw.agents.tools.web_search import web_search; from quantclaw.state.plans import PlanStore; from quantclaw.state.event_persister import EventPersister; print('All imports OK')"`

**Step 3: Commit plan**

```bash
git add docs/plans/2026-04-05-orchestration-activation-impl.md
git commit -m "docs: add orchestration activation implementation plan"
```

---

## Summary of Files Created/Modified

### Created (8 files):
| File | Purpose |
|------|---------|
| `quantclaw/state/plans.py` | Plan persistence (SQLite CRUD) |
| `quantclaw/state/event_persister.py` | Batched event persistence to SQLite |
| `quantclaw/agents/tools/web_search.py` | Shared web search tool (DuckDuckGo/Brave/Tavily) |
| `quantclaw/dashboard/app/app/dashboard/chat/useChatStream.ts` | WebSocket hook for chat narrative streaming |
| `tests/test_ollama_router.py` | Ollama provider tests |
| `tests/test_cancellation.py` | Plan cancellation tests |
| `tests/test_plan_persistence.py` | Plan + event persistence tests |
| `tests/test_persistence.py` | Goal + autonomy mode persistence tests |
| `tests/test_web_search.py` | Web search tool tests |
| `tests/test_ooda_activation.py` | OODA run_cycle + run_continuous tests |
| `tests/test_activation_integration.py` | Full activation integration tests |

### Modified (8 files):
| File | Change |
|------|--------|
| `quantclaw/events/types.py` | +2 event types (CHAT_NARRATIVE, ORCHESTRATION_CYCLE_COMPLETE) |
| `quantclaw/config/default.yaml` | +orchestration config, +search config, +ollama provider |
| `quantclaw/orchestrator/router.py` | +Ollama provider support |
| `quantclaw/orchestrator/dispatcher.py` | +cancellation token support |
| `quantclaw/state/db.py` | +plans table in schema |
| `quantclaw/orchestration/ooda.py` | +run_cycle, +run_continuous, +cycle tracking, +persistent goal |
| `quantclaw/orchestration/autonomy.py` | +playbook persistence, +from_playbook() |
| `quantclaw/dashboard/api.py` | Lifespan activation, app.state, chat routing, stop endpoint |
| `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts` | +chat.narrative, +cycle_complete handlers |
