# Scheduler Intelligence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Scheduler iteratively intelligent — it evaluates results, decides whether to pursue/iterate/abandon, balances exploration vs exploitation, narrates its reasoning in chat, and provides a Log page on the dashboard.

**Architecture:** Enhance the existing OODA loop with `_evaluate_results()`, `_get_exploration_mode()`, and `_iteration_context`. Enrich event payloads with reasoning. Extend events API with filters. Add Log page to frontend.

**Tech Stack:** Python 3.12+ (asyncio, dataclasses), FastAPI, Next.js/TypeScript

---

## Task 1: New Event Type + Config

**Files:**
- Modify: `quantclaw/events/types.py`
- Modify: `quantclaw/config/default.yaml`

**Step 1: Add event type**

Add to `EventType` enum in `quantclaw/events/types.py`:

```python
    ORCHESTRATION_EVALUATION = "orchestration.evaluation"
```

**Step 2: Add exploration config to `quantclaw/config/default.yaml`**

Add inside the existing `orchestration:` section (after `ooda_interval: 30`):

```yaml
  max_iterations_per_cycle: 3
  exploration:
    explore_temp: 0.7
    exploit_temp: 0.2
    balanced_temp: 0.4
    high_explore_until: 5
    balanced_until: 15
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_events.py tests/test_config.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/events/types.py quantclaw/config/default.yaml
git commit -m "feat: add orchestration.evaluation event type and exploration config"
```

---

## Task 2: Exploration Mode + Result Evaluation

The core intelligence: determine explore/exploit mode and evaluate results.

**Files:**
- Modify: `quantclaw/orchestration/ooda.py`
- Create: `tests/test_scheduler_intelligence.py`

**Step 1: Write the failing tests**

```python
# tests/test_scheduler_intelligence.py
"""Tests for Scheduler intelligence: exploration mode and result evaluation."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook, EntryType
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool


class StubAgent(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "stub", "sharpe": 0.5})


def _make(tmp_path, mode=AutonomyMode.AUTOPILOT):
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    config = {
        "orchestration": {
            "max_iterations_per_cycle": 3,
            "exploration": {
                "explore_temp": 0.7,
                "exploit_temp": 0.2,
                "balanced_temp": 0.4,
                "high_explore_until": 5,
                "balanced_until": 15,
            },
        },
    }
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=mode),
                    dispatcher=dispatcher, config=config)
    return bus, pb, ooda


def test_exploration_mode_empty_playbook(tmp_path):
    _, pb, ooda = _make(tmp_path)

    async def _run():
        mode, temp = await ooda._get_exploration_mode()
        assert mode == "explore"
        assert temp == 0.7

    asyncio.run(_run())


def test_exploration_mode_medium_playbook(tmp_path):
    _, pb, ooda = _make(tmp_path)

    async def _run():
        for i in range(10):
            await pb.add(EntryType.STRATEGY_RESULT, {"sharpe": i * 0.1}, tags=["test"])
        mode, temp = await ooda._get_exploration_mode()
        assert mode == "balanced"
        assert temp == 0.4

    asyncio.run(_run())


def test_exploration_mode_large_playbook(tmp_path):
    _, pb, ooda = _make(tmp_path)

    async def _run():
        for i in range(20):
            await pb.add(EntryType.STRATEGY_RESULT, {"sharpe": i * 0.1}, tags=["test"])
        mode, temp = await ooda._get_exploration_mode()
        assert mode == "exploit"
        assert temp == 0.2

    asyncio.run(_run())


def test_evaluate_results_no_history(tmp_path):
    """With < 3 playbook entries, percentile is None."""
    _, pb, ooda = _make(tmp_path)

    async def _run():
        results = {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 1.0})}
        evaluation = await ooda._evaluate_results(results, iteration=1)
        assert evaluation["percentile"] is None
        assert "verdict" in evaluation

    asyncio.run(_run())


def test_evaluate_results_with_history(tmp_path):
    """With enough history, percentile is calculated."""
    _, pb, ooda = _make(tmp_path)

    async def _run():
        for s in [0.2, 0.5, 0.8, 1.0, 1.2]:
            await pb.add(EntryType.STRATEGY_RESULT, {"sharpe": s}, tags=["test"])

        results = {0: AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 1.5})}
        evaluation = await ooda._evaluate_results(results, iteration=1)
        assert evaluation["percentile"] is not None
        assert evaluation["percentile"] == 1.0  # Better than all 5

    asyncio.run(_run())


def test_iteration_context_accumulates(tmp_path):
    _, pb, ooda = _make(tmp_path)

    async def _run():
        assert len(ooda._iteration_context) == 0
        ooda._iteration_context.append({
            "iteration": 1,
            "results": {"sharpe": 0.3},
            "verdict": "iterate",
            "suggestion": "try volatility",
        })
        assert len(ooda._iteration_context) == 1

    asyncio.run(_run())
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scheduler_intelligence.py -v`
Expected: FAIL — `_get_exploration_mode` and `_evaluate_results` don't exist

**Step 3: Add methods to `quantclaw/orchestration/ooda.py`**

Read the current file first. Add these to the OODALoop class:

1. Add to `__init__`:
```python
self._iteration_context: list[dict] = []
self._llm_call_count = 0
```

2. Add `_get_exploration_mode` method:
```python
async def _get_exploration_mode(self) -> tuple[str, float]:
    """Determine explore/exploit mode based on Playbook maturity."""
    orch_cfg = self._config.get("orchestration", {})
    explore_cfg = orch_cfg.get("exploration", {})
    high_until = explore_cfg.get("high_explore_until", 5)
    balanced_until = explore_cfg.get("balanced_until", 15)

    all_results = await self._playbook.query(entry_type=EntryType.STRATEGY_RESULT)
    playbook_size = len(all_results)

    if playbook_size < high_until:
        return "explore", explore_cfg.get("explore_temp", 0.7)
    elif playbook_size < balanced_until:
        return "balanced", explore_cfg.get("balanced_temp", 0.4)
    else:
        return "exploit", explore_cfg.get("exploit_temp", 0.2)
```

3. Add `_evaluate_results` method:
```python
async def _evaluate_results(self, results: dict, iteration: int) -> dict:
    """Evaluate cycle results: percentile ranking + LLM judgment.

    Returns: {verdict, reasoning, suggestion, percentile}
    """
    # Extract best sharpe from results
    best_sharpe = 0.0
    best_result = {}
    for step_id, result in results.items():
        if result.status == AgentStatus.SUCCESS:
            sharpe = result.data.get("sharpe", 0)
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_result = result.data

    # Step 1: Playbook percentile
    past = await self._playbook.query(entry_type=EntryType.STRATEGY_RESULT)
    past_sharpes = [e.content.get("sharpe", 0) for e in past]

    percentile = None
    percentile_note = "Not enough history for comparison. Evaluate on absolute metrics."
    if len(past_sharpes) >= 3:
        percentile = sum(1 for s in past_sharpes if best_sharpe > s) / len(past_sharpes)
        percentile_note = f"Top {(1 - percentile) * 100:.0f}% of {len(past_sharpes)} past strategies"

    max_iterations = self._config.get("orchestration", {}).get("max_iterations_per_cycle", 3)

    # Step 2: LLM judgment (try, fallback to heuristic)
    try:
        from quantclaw.orchestrator.router import LLMRouter
        router = LLMRouter(self._config)

        prompt = (
            f"You are evaluating strategy results.\n\n"
            f"Result: {json.dumps(best_result)}\n"
            f"Percentile: {percentile_note}\n"
            f"Previous iterations this cycle: {json.dumps(self._iteration_context)}\n"
            f"Iteration {iteration} of {max_iterations}\n\n"
            f"Should we:\n"
            f"- pursue: results are strong enough to act on\n"
            f"- iterate: promising but could improve, suggest refinement\n"
            f"- abandon: not worth continuing, try something different\n\n"
            f"{'If this is the last iteration, you MUST choose pursue or abandon.' if iteration >= max_iterations else ''}\n\n"
            f"Respond as JSON: {{\"verdict\": str, \"reasoning\": str, \"suggestion\": str}}"
        )

        response = await router.call(
            "scheduler",
            messages=[{"role": "user", "content": prompt}],
            system="You are a quantitative strategy evaluator. Respond only with valid JSON.",
            temperature=0.2,
        )
        self._llm_call_count += 1

        evaluation = json.loads(response)
    except Exception:
        # Heuristic fallback
        if iteration >= max_iterations:
            verdict = "pursue" if best_sharpe > 0 else "abandon"
        elif best_sharpe > 1.0:
            verdict = "pursue"
        elif best_sharpe > 0.3:
            verdict = "iterate"
        else:
            verdict = "abandon"
        evaluation = {
            "verdict": verdict,
            "reasoning": f"Heuristic: sharpe={best_sharpe:.2f}",
            "suggestion": "Try a different approach" if verdict == "abandon" else "Refine parameters",
        }

    evaluation["percentile"] = percentile
    evaluation["best_result"] = best_result

    # Emit evaluation event
    await self._bus.publish(Event(
        type=EventType.ORCHESTRATION_EVALUATION,
        payload={
            "plan_id": "",
            "iteration": iteration,
            "verdict": evaluation["verdict"],
            "percentile": percentile,
            "results": best_result,
            "reasoning": evaluation.get("reasoning", ""),
            "suggestion": evaluation.get("suggestion", ""),
        },
        source_agent="scheduler",
    ))

    return evaluation
```

Make sure `json` is imported at the top of the file (it should already be).

**Step 4: Run tests**

Run: `python -m pytest tests/test_scheduler_intelligence.py -v`
Expected: All 7 PASS

**Step 5: Commit**

```bash
git add quantclaw/orchestration/ooda.py tests/test_scheduler_intelligence.py
git commit -m "feat: add exploration mode and result evaluation to OODA loop"
```

---

## Task 3: Iterative run_cycle

Enhance `run_cycle()` with the evaluate-iterate loop.

**Files:**
- Modify: `quantclaw/orchestration/ooda.py`
- Create: `tests/test_iterative_cycle.py`

**Step 1: Write the failing test**

```python
# tests/test_iterative_cycle.py
"""Tests for iterative run_cycle with evaluate loop."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
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
        return AgentResult(status=AgentStatus.SUCCESS, data={"sharpe": 0.5, "result": "data"})


def _make(tmp_path):
    bus = EventBus()
    pb = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    config = {
        "orchestration": {
            "max_iterations_per_cycle": 3,
            "exploration": {
                "explore_temp": 0.7,
                "exploit_temp": 0.2,
                "balanced_temp": 0.4,
                "high_explore_until": 5,
                "balanced_until": 15,
            },
        },
    }
    ooda = OODALoop(bus=bus, playbook=pb, trust=TrustManager(),
                    autonomy=AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT),
                    dispatcher=dispatcher, config=config)
    return bus, pb, ooda


def test_iterative_cycle_runs(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    events = []
    async def capture(event):
        events.append(str(event.type))
    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle(chat_history=[])
        await asyncio.sleep(0.1)

    asyncio.run(_run())

    # Should have evaluation event(s)
    assert "orchestration.evaluation" in events
    assert "orchestration.cycle_complete" in events


def test_iterative_cycle_clears_context(tmp_path):
    """Iteration context should be cleared between cycles."""
    _, _, ooda = _make(tmp_path)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle()
        assert len(ooda._iteration_context) == 0  # Cleared after cycle

    asyncio.run(_run())


def test_iterative_cycle_enriched_events(tmp_path):
    bus, pb, ooda = _make(tmp_path)

    payloads = []
    async def capture(event):
        if str(event.type) == "orchestration.cycle_complete":
            payloads.append(event.payload)
    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": {"query": "test"}})
        await ooda.run_cycle()
        await asyncio.sleep(0.1)

    asyncio.run(_run())

    assert len(payloads) >= 1
    p = payloads[0]
    assert "iterations" in p
    assert "llm_calls" in p
    assert "exploration_mode" in p
```

**Step 2: Update `run_cycle()` in `quantclaw/orchestration/ooda.py`**

Read the current `run_cycle()` method. Replace it with the iterative version:

```python
async def run_cycle(self, chat_history: list[dict] | None = None) -> dict | None:
    """Run a single OODA cycle with iterative evaluation.

    The evaluate → decide → act loop can repeat up to max_iterations_per_cycle.
    """
    max_iterations = self._config.get("orchestration", {}).get("max_iterations_per_cycle", 3)
    self._iteration_context = []  # Reset per cycle
    self._llm_call_count = 0

    # Get exploration mode
    exploration_mode, exploration_temp = await self._get_exploration_mode()

    # Observe
    state = await self.observe()
    if chat_history:
        max_history = self._config.get("orchestration", {}).get("max_chat_history", 10)
        state["chat_history"] = chat_history[-max_history:]

    best_results = None
    best_evaluation = None

    for iteration in range(1, max_iterations + 1):
        # Orient
        orientation = await self.orient(state)

        # Inject iteration context into orientation for the Planner
        if self._iteration_context:
            orientation["iteration_context"] = self._iteration_context
        orientation["exploration_mode"] = exploration_mode
        orientation["exploration_temp"] = exploration_temp

        # Decide
        plan = await self.decide(orientation)
        if plan is None:
            break

        # Act
        results = await self.act(plan)

        # Evaluate
        evaluation = await self._evaluate_results(results, iteration)
        verdict = evaluation.get("verdict", "pursue")

        # Narrate
        await self._bus.publish(Event(
            type=EventType.CHAT_NARRATIVE,
            payload={
                "message": f"Iteration {iteration}: {evaluation.get('reasoning', '')}",
                "role": "scheduler",
            },
            source_agent="scheduler",
        ))

        if verdict == "pursue":
            best_results = results
            best_evaluation = evaluation
            break
        elif verdict == "iterate" and iteration < max_iterations:
            # Accumulate context for next iteration
            self._iteration_context.append({
                "iteration": iteration,
                "results": evaluation.get("best_result", {}),
                "verdict": verdict,
                "suggestion": evaluation.get("suggestion", ""),
            })
            # May update exploration mode per-iteration (LLM override)
            if evaluation.get("suggestion"):
                exploration_mode = "exploit"
                exploration_temp = self._config.get(
                    "orchestration", {}).get("exploration", {}).get("exploit_temp", 0.2)
            best_results = results
            best_evaluation = evaluation
            continue
        else:
            # abandon or last iteration
            best_results = results
            best_evaluation = evaluation
            break

    if best_results is None:
        await self.sleep()
        return None

    self._cycle_count += 1

    # Learn from best results
    for step_id, result in best_results.items():
        if result.status == AgentStatus.SUCCESS and result.data:
            entry_type = "strategy_result"
            if best_evaluation and best_evaluation.get("verdict") == "abandon":
                entry_type = "what_failed"
            await self.learn({
                "type": entry_type,
                "content": result.data,
                "tags": ["auto", exploration_mode],
            })

    # Emit enriched cycle complete
    await self._bus.publish(Event(
        type=EventType.ORCHESTRATION_CYCLE_COMPLETE,
        payload={
            "cycle": self._cycle_count,
            "plan_id": "",
            "iterations": len(self._iteration_context) + 1,
            "llm_calls": self._llm_call_count,
            "exploration_mode": exploration_mode,
            "temperature": exploration_temp,
            "verdict": best_evaluation.get("verdict", "pursue") if best_evaluation else "none",
            "percentile": best_evaluation.get("percentile") if best_evaluation else None,
            "reasoning": best_evaluation.get("reasoning", "") if best_evaluation else "",
            "steps_completed": len([r for r in best_results.values()
                                     if r.status == AgentStatus.SUCCESS]),
        },
        source_agent="scheduler",
    ))

    # Summary narration
    verdict = best_evaluation.get("verdict", "") if best_evaluation else ""
    percentile = best_evaluation.get("percentile") if best_evaluation else None
    pct_str = f"top {(1 - percentile) * 100:.0f}%" if percentile is not None else "no history"
    iterations = len(self._iteration_context) + 1

    await self._bus.publish(Event(
        type=EventType.CHAT_NARRATIVE,
        payload={
            "message": (
                f"Completed {iterations} iteration{'s' if iterations > 1 else ''}. "
                f"Verdict: {verdict} ({pct_str}). "
                f"{self._llm_call_count} LLM calls used."
            ),
            "role": "scheduler",
        },
        source_agent="scheduler",
    ))

    self._iteration_context = []  # Clear for next cycle
    await self.sleep()
    return best_results
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_iterative_cycle.py tests/test_ooda.py tests/test_ooda_activation.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/orchestration/ooda.py tests/test_iterative_cycle.py
git commit -m "feat: add iterative evaluate loop to run_cycle with enriched events"
```

---

## Task 4: Enriched Planner Prompt

Pass Playbook context, iteration context, and exploration mode into the Planner.

**Files:**
- Modify: `quantclaw/orchestrator/planner.py`
- Modify: `quantclaw/orchestration/ooda.py` (update `decide()` to pass context)

**Step 1: Read current `quantclaw/orchestrator/planner.py`**

The Planner has a hardcoded system prompt. Enhance it to accept dynamic context.

**Step 2: Update `Planner.create_plan()` to accept context**

Add an optional `context` parameter:

```python
async def create_plan(self, request: str, context: dict | None = None) -> Plan:
    """Decompose a request into a Plan with steps."""
    playbook_section = ""
    iteration_section = ""
    exploration_section = ""

    if context:
        if context.get("playbook_context"):
            entries = context["playbook_context"][:5]
            playbook_section = "\n\nPlaybook (recent knowledge):\n"
            for e in entries:
                playbook_section += f"- [{e.get('type', '')}] {str(e.get('content', ''))[:200]}\n"

        if context.get("iteration_context"):
            iteration_section = "\n\nPrevious iterations this cycle:\n"
            for ic in context["iteration_context"]:
                iteration_section += (
                    f"- Iteration {ic['iteration']}: {ic.get('verdict', '')} — "
                    f"{ic.get('suggestion', '')}\n"
                )

        if context.get("exploration_mode"):
            mode = context["exploration_mode"]
            temp = context.get("exploration_temp", 0.5)
            exploration_section = (
                f"\n\nExploration mode: {mode} (temperature {temp}). "
                f"You may override to explore|exploit|balanced if needed. "
                f"If exploring, try unconventional approaches. "
                f"If exploiting, refine what's working.\n"
            )

    system = (
        "You are the QuantClaw planner. Decompose user requests into agent tasks.\n"
        "Available agents: ingestor, miner, backtester, researcher, executor, "
        "reporter, trainer, compliance, cost_tracker, debugger.\n"
        "Return a JSON array of {\"agent\": str, \"task\": dict, \"description\": str, "
        "\"depends_on\": list[int]} objects.\n"
        "Each step has a sequential id starting from 0. depends_on references step ids.\n"
        "You have full creative latitude — invent new approaches, try unconventional "
        "combinations, run parallel experiments.\n"
        "Return ONLY valid JSON, no markdown or explanation."
        f"{playbook_section}{iteration_section}{exploration_section}"
    )

    # ... rest of method unchanged, but pass temperature if in context
    temp = context.get("exploration_temp", None) if context else None
    response = await self._router.call(
        "planner",  # "planner" is a model assignment, not a registered agent
        messages=[{"role": "user", "content": request}],
        system=system,
        temperature=temp,
    )

    # ... rest unchanged
```

**Step 3: Update `decide()` in ooda.py to pass context**

In the `decide()` method, when calling `planner.create_plan()`, pass the orientation context:

```python
plan = await planner.create_plan(planner_request, context={
    "playbook_context": orientation.get("playbook_context", []),
    "iteration_context": orientation.get("iteration_context", []),
    "exploration_mode": orientation.get("exploration_mode", ""),
    "exploration_temp": orientation.get("exploration_temp", 0.5),
})
```

**Step 4: Run tests**

Run: `python -m pytest tests/ -v --tb=short 2>&1 | tail -5`
Expected: All PASS

**Step 5: Commit**

```bash
git add quantclaw/orchestrator/planner.py quantclaw/orchestration/ooda.py
git commit -m "feat: enrich Planner prompt with Playbook, iteration, and exploration context"
```

---

## Task 5: Events API Filters

Extend `GET /api/events` with query parameters for the Log page.

**Files:**
- Modify: `quantclaw/dashboard/api.py`
- Create: `tests/test_events_api.py`

**Step 1: Write the failing test**

```python
# tests/test_events_api.py
"""Tests for events API with filters."""
from fastapi.testclient import TestClient


def test_events_default():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_events_with_limit():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events?limit=5")
    assert resp.status_code == 200


def test_events_with_agent_filter():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events?agent=scheduler")
    assert resp.status_code == 200


def test_events_with_type_filter():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/events?type=orchestration.*")
    assert resp.status_code == 200
```

**Step 2: Update the events endpoint in `quantclaw/dashboard/api.py`**

Read the current `get_events` endpoint. Replace with:

```python
@app.get("/api/events")
def get_events(limit: int = 50, offset: int = 0, agent: str = "",
               type: str = "", since: str = ""):
    """Get events with optional filters."""
    recent = _bus.recent(500)  # Get a larger window for filtering

    filtered = recent
    if agent:
        filtered = [e for e in filtered if e.source_agent == agent]
    if type:
        import fnmatch
        filtered = [e for e in filtered if fnmatch.fnmatch(str(e.type), type)]
    if since:
        filtered = [e for e in filtered if e.timestamp.isoformat() >= since]

    # Apply offset and limit
    filtered = filtered[offset:offset + limit]

    return {"events": [{"type": str(e.type), "payload": e.payload,
                        "source_agent": e.source_agent,
                        "timestamp": e.timestamp.isoformat()} for e in filtered],
            "total": len(recent)}
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_events_api.py tests/test_dashboard_api.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/dashboard/api.py tests/test_events_api.py
git commit -m "feat: add filter params to events API (agent, type, since, limit)"
```

---

## Task 6: Frontend — Log Page + Sidebar

Add the Log page and navigation.

**Files:**
- Create: `quantclaw/dashboard/app/app/dashboard/logs/page.tsx`
- Modify: `quantclaw/dashboard/app/app/dashboard/layout.tsx`
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts`

**Step 1: Read the current layout.tsx to understand the sidebar structure**

**Step 2: Add Logs to sidebar navigation in layout.tsx**

Find the sidebar nav items. Add a Logs entry between Agents and Risk (or wherever Risk appears):

```typescript
{ name: "Logs", href: "/dashboard/logs", icon: "..." }
```

Match the existing pattern for icons and styling.

**Step 3: Create the Log page**

Read `quantclaw/dashboard/app/AGENTS.md` first — it warns about Next.js breaking changes.

Create `quantclaw/dashboard/app/app/dashboard/logs/page.tsx`:

```typescript
"use client";
import { useState, useEffect, useCallback } from "react";

const API_URL = "http://localhost:8000/api/events";
const POLL_INTERVAL = 5000;

interface EventEntry {
  type: string;
  payload: Record<string, unknown>;
  source_agent: string;
  timestamp: string;
}

const EVENT_TYPE_OPTIONS = [
  { label: "All Events", value: "" },
  { label: "Orchestration", value: "orchestration.*" },
  { label: "Agent", value: "agent.*" },
  { label: "Chat", value: "chat.*" },
  { label: "Market", value: "market.*" },
  { label: "Trade", value: "trade.*" },
];

const AGENT_OPTIONS = [
  "", "scheduler", "researcher", "backtester", "miner",
  "ingestor", "executor", "reporter", "trainer",
  "risk_monitor", "sentinel", "compliance", "cost_tracker", "debugger",
];

const TIME_RANGES = [
  { label: "All", value: "" },
  { label: "Today", value: "today" },
  { label: "Last 24h", value: "24h" },
  { label: "Last 7d", value: "7d" },
];

function getSinceDate(range: string): string {
  if (!range) return "";
  const now = new Date();
  if (range === "today") {
    return now.toISOString().split("T")[0];
  }
  if (range === "24h") {
    return new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  }
  if (range === "7d") {
    return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
  }
  return "";
}

function formatPayload(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  if (payload.reasoning) parts.push(String(payload.reasoning));
  if (payload.verdict) parts.push(`Verdict: ${payload.verdict}`);
  if (payload.message) parts.push(String(payload.message));
  if (payload.exploration_mode) parts.push(`Mode: ${payload.exploration_mode} (temp ${payload.temperature})`);
  if (payload.sharpe || payload.result_summary) {
    const summary = (payload.result_summary || payload) as Record<string, unknown>;
    if (summary.sharpe) parts.push(`Sharpe: ${summary.sharpe}`);
  }
  if (payload.error) parts.push(`Error: ${payload.error}`);
  if (parts.length === 0) {
    const str = JSON.stringify(payload);
    return str.length > 200 ? str.slice(0, 200) + "..." : str;
  }
  return parts.join(" | ");
}

function typeColor(type: string): string {
  if (type.startsWith("orchestration.")) return "#60a5fa";
  if (type.startsWith("agent.task_completed")) return "#34d399";
  if (type.startsWith("agent.task_failed")) return "#f87171";
  if (type.startsWith("agent.")) return "#a78bfa";
  if (type.startsWith("chat.")) return "#fbbf24";
  if (type.startsWith("market.")) return "#f472b6";
  return "#9ca3af";
}

export default function LogsPage() {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [timeRange, setTimeRange] = useState("");

  const fetchEvents = useCallback(async () => {
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (typeFilter) params.set("type", typeFilter);
    if (agentFilter) params.set("agent", agentFilter);
    const since = getSinceDate(timeRange);
    if (since) params.set("since", since);

    try {
      const resp = await fetch(`${API_URL}?${params}`);
      const data = await resp.json();
      setEvents((data.events || []).reverse());
    } catch {}
  }, [typeFilter, agentFilter, timeRange]);

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  return (
    <div style={{ padding: "24px", fontFamily: "monospace", color: "#e5e7eb", maxWidth: 900 }}>
      <h1 style={{ fontSize: 24, marginBottom: 16 }}>Logs</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
                style={{ background: "#1f2937", color: "#e5e7eb", border: "1px solid #374151", padding: "6px 10px", borderRadius: 6 }}>
          {EVENT_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}
                style={{ background: "#1f2937", color: "#e5e7eb", border: "1px solid #374151", padding: "6px 10px", borderRadius: 6 }}>
          <option value="">All Agents</option>
          {AGENT_OPTIONS.filter(Boolean).map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select value={timeRange} onChange={(e) => setTimeRange(e.target.value)}
                style={{ background: "#1f2937", color: "#e5e7eb", border: "1px solid #374151", padding: "6px 10px", borderRadius: 6 }}>
          {TIME_RANGES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {events.length === 0 && (
          <div style={{ color: "#6b7280", padding: 20, textAlign: "center" }}>No events found</div>
        )}
        {events.map((e, i) => {
          const time = new Date(e.timestamp).toLocaleTimeString();
          return (
            <div key={i} style={{ padding: "8px 12px", borderLeft: `3px solid ${typeColor(e.type)}`,
                                  background: "#111827", borderRadius: 4, fontSize: 13 }}>
              <div style={{ display: "flex", gap: 12, color: "#9ca3af" }}>
                <span>{time}</span>
                <span style={{ color: "#d1d5db" }}>{e.source_agent || "—"}</span>
                <span style={{ color: typeColor(e.type) }}>{e.type}</span>
              </div>
              <div style={{ color: "#d1d5db", marginTop: 4, fontSize: 12 }}>
                {formatPayload(e.payload)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 4: Add `orchestration.evaluation` handler to useFloorEvents.ts**

Add to the switch statement:

```typescript
case "orchestration.evaluation": {
  const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
  if (schedulerIdx >= 0) {
    const verdict = (event.payload?.verdict as string) || "";
    updated[schedulerIdx] = {
      ...updated[schedulerIdx],
      speechBubble: `Eval: ${verdict}`,
    };
  }
  break;
}
```

**Step 5: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/logs/page.tsx quantclaw/dashboard/app/app/dashboard/layout.tsx quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts
git commit -m "feat: add Log page to dashboard with filters and auto-refresh"
```

---

## Task 7: Final Verification

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: Verify imports**

Run: `python -c "from quantclaw.orchestration.ooda import OODALoop; print('exploration mode:', OODALoop.__dict__.keys()); print('OK')"`

**Step 3: Commit plan**

```bash
git add docs/plans/2026-04-06-scheduler-intelligence-impl.md
git commit -m "docs: add scheduler intelligence implementation plan"
```

---

## Summary

### Created (4 files):
| File | Purpose |
|------|---------|
| `tests/test_scheduler_intelligence.py` | Exploration mode + evaluation tests (7 tests) |
| `tests/test_iterative_cycle.py` | Iterative run_cycle tests (3 tests) |
| `tests/test_events_api.py` | Events API filter tests (4 tests) |
| `quantclaw/dashboard/app/app/dashboard/logs/page.tsx` | Log page with filters + auto-refresh |

### Modified (5 files):
| File | Change |
|------|--------|
| `quantclaw/events/types.py` | +ORCHESTRATION_EVALUATION event type |
| `quantclaw/config/default.yaml` | +max_iterations_per_cycle, +exploration config |
| `quantclaw/orchestration/ooda.py` | +_evaluate_results, +_get_exploration_mode, +iterative run_cycle |
| `quantclaw/orchestrator/planner.py` | +context param with playbook/iteration/exploration |
| `quantclaw/dashboard/api.py` | +filter params on events endpoint |
| `quantclaw/dashboard/app/app/dashboard/layout.tsx` | +Logs sidebar nav item |
| `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts` | +orchestration.evaluation handler |
