# Orchestration Engine Activation — Design Document

**Date:** 2026-04-05
**Status:** Approved (v5 — final audit)
**Author:** Harry + Claude
**Depends on:** Orchestration Engine (implemented, not activated)

## Problem

The orchestration engine (OODA loop, playbook, trust, autonomy modes) is fully implemented and tested (126 tests passing) but not activated. The OODA loop runs nowhere. Chat messages bypass the Scheduler entirely and go directly to an LLM. Half the orchestration state is ephemeral and lost on restart.

## Solution: Five Parts

### Part 1: Activation

Merge the OODA loop into the API server process as a background `asyncio.Task` inside FastAPI's lifespan. Chat messages route through the Scheduler (OODA loop) instead of directly to an LLM.

**Startup sequence (FastAPI lifespan):**
1. Load config
2. Open SQLite database (WAL mode enabled)
3. Create Playbook
4. Restore TrustManager from playbook (with EventBus)
5. Restore goal + autonomy mode from playbook
6. Create AgentPool, register all agents
7. Create Dispatcher (with EventBus, cancellation support)
8. Create OODA loop (with all dependencies)
9. Restore pending tasks from SQLite TaskStore into OODA
10. Restore in-progress plans from SQLite plans table
11. Subscribe EventBus → SQLite batch persistence handler
12. Start OODA loop as `asyncio.Task` (runs continuously, auto-restarts on crash)

**IMPORTANT:** All orchestration objects are created inside the lifespan function (not at module level) because they depend on the SQLite database which is async. The module-level `_ooda`, `_trust`, etc. from the previous implementation are replaced with lifespan-scoped references stored on `app.state`. Existing orchestration endpoints (`/api/orchestration/*`) are updated to use `request.app.state.ooda` instead of module-level variables.

**Chat flow (streaming via WebSocket):**

The `/api/chat` endpoint works in two modes:

```
CEO types: "find me momentum strategies"
  → POST /api/chat (no @agent prefix)
  → Scheduler receives as CEO intent (with last 10 chat messages as context)
  → Returns immediately: {"status": "orchestrating", "agent": "scheduler"}
  → Frontend recognizes "orchestrating" status → starts listening for WebSocket narrative
  → OODA cycle runs in background:
    1. Scheduler narrates plan → WebSocket: chat.narrative event
       Chat panel appends: "Here's my plan: 1) Research momentum factors, 2) Backtest candidates..."
    2. Step starts → WebSocket: orchestration.step_started (agent lights up on floor)
       Chat panel appends: "Researching momentum factors..."
    3. Step completes → Scheduler LLM summarizes result → WebSocket: chat.narrative
       Chat panel appends: "Found 3 promising approaches: mean reversion, momentum 5d, volatility breakout"
    4. Next step starts → WebSocket: orchestration.step_started
    5. All steps done → Scheduler LLM generates final summary → WebSocket: chat.narrative
       Chat panel appends: "Summary: Momentum 5d scored highest with Sharpe 1.5..."
    6. → WebSocket: orchestration.cycle_complete (chat panel knows cycle is done)

CEO types: "@backtester run momentum_5d"
  → POST /api/chat (has @agent prefix)
  → Direct agent chat, bypasses orchestration (existing behavior)
  → Returns: {"response": "...", "agent": "backtester"}
```

**New WebSocket event types needed:**
- `chat.narrative` — carries `{message: str, role: "scheduler"}` for the chat panel to render
- `orchestration.cycle_complete` — signals that the current OODA cycle is finished

**Narrative generation:** After each step completes, the Scheduler calls the LLM (at temperature 0.3) with the step's result data and asks for a human-readable summary. This is a lightweight LLM call — just summarization, not planning.

**The Scheduler is the gateway.** All agent activity flows through it:
- CEO chat messages → Scheduler decides what to do
- Cron triggers → feed into OODA as pending tasks
- Market events → wake the OODA loop
- Agent completions → trigger next OODA cycle

### Part 2: Completion Model & Cancellation

**Chat-triggered (one-shot):**
- CEO sends a message → one OODA cycle → plan executes → results reported → done
- Scheduler goes back to sleep, waits for next trigger
- If CEO wants more: "keep going" or "try something different" → another cycle

**Autonomous goal (standing order in autopilot):**
- CEO sets a standing goal: "continuously find profitable strategies"
- Scheduler keeps cycling on its own
- Bounded by safety nets (inspired by OpenClaw depth limits + DeerFlow loop detection):
  - `max_cycles_per_goal`: default 3 — mandatory CEO checkpoint after 3 cycles
  - `cycle_timeout_minutes`: default 20 — per-cycle time limit
  - Loop detection: vector similarity comparison of plan embeddings (see below)
- After each cycle, reports progress via `chat.narrative`
- After 3 cycles, checkpoints with CEO: "Here's what I've found so far. Want me to keep exploring?"
- CEO can intervene anytime: "stop", "switch to plan mode", kill switch

**Completion model (from OpenClaw/DeerFlow research):**

The DAG is the natural unit of work. A well-formed plan has an end. No complex "am I done?" logic needed — when the DAG completes, the job is done. Safety nets only catch edge cases.

| Scenario | Behavior |
|---|---|
| CEO sends message | One plan → execute all steps → report → wait |
| CEO says "keep going" | Another plan → execute → report → wait |
| Autopilot + standing goal | Plan → execute → learn → next plan → max 3 cycles then checkpoint |
| Market event | One reactive plan → execute → report |

No recursive plan generation — the Scheduler cannot spawn another Scheduler. Each plan is a flat DAG of agent tasks with finite steps.

**Stop button / cancellation:**

A stop button (similar to Claude Code / Cursor) cancels any in-progress workflow immediately.

```
CEO clicks Stop (or sends "stop")
  → POST /api/orchestration/stop
  → Cancellation event is set → Dispatcher checks between steps
  → All running agent tasks are cancelled via asyncio.Task.cancel()
  → Current plan recorded to Playbook as INCOMPLETE (not failure)
  → chat.narrative: "Workflow stopped."
  → orchestration.cycle_complete sent
  → OODA returns to sleep, awaits next trigger
```

Mechanical implementation: `asyncio.Event` as a cancellation token, passed to the Dispatcher. The Dispatcher checks `cancel_event.is_set()` before starting each step. Running agent tasks are wrapped in cancellable `asyncio.Task` objects. The `/api/orchestration/stop` endpoint sets the cancel event.

```python
# In Dispatcher.execute_plan()
async def run_step(step):
    if self._cancel_event and self._cancel_event.is_set():
        step.status = StepStatus.SKIPPED
        return step.id, AgentResult(status=AgentStatus.FAILED, error="Cancelled")
    # ... execute step
```

**Loop detection (vector similarity):**

When the Scheduler generates a new plan in autopilot mode, compare it to previous plans in the current goal session using vector similarity:

```
New plan generated
  → Compute embedding of plan description + step descriptions
  → Compare to embeddings of previous plans in this goal session
  → If cosine similarity > 0.85 with any previous plan:
    → Stop cycling, report to CEO: "I'm generating similar plans. Here's what I have so far."
  → If similarity < 0.85:
    → Plan is sufficiently different, proceed
```

Embedding computed via the configured LLM (a short embedding call). If no embedding model available, fall back to simple hash comparison of `(agent, description)` tuples.

**Cycle limits configuration:**
```yaml
orchestration:
  max_cycles_per_goal: 3
  cycle_timeout_minutes: 20
  ooda_interval: 30  # seconds between cycles when idle
  max_chat_history: 10  # messages passed to Scheduler LLM
  max_debugger_retries: 5  # per failed step
  loop_similarity_threshold: 0.85  # cosine similarity for loop detection
```

**Kill switch always works** — forces mode to PLAN, halts all pending tasks, cancels running agents.

### Part 3: Conversation Context, Error Recovery & Search

**Conversation context (sliding window):**

The Scheduler needs chat history to understand follow-ups like "no, try bonds instead." But too much history overwhelms the LLM and wastes tokens.

Approach (OpenClaw-style sliding window):
- Last 10 chat messages passed to the Scheduler in the orient/decide phase
- No summarization — just drop oldest (simple, predictable, no extra LLM cost)
- The Playbook serves as long-term memory for strategy results and learnings
- Chat history is conversational context; Playbook is domain knowledge

```
/api/chat receives message with history[]:
  → Take last 10 messages from history
  → Pass to OODA orient() as conversation_context
  → Planner receives: goal + playbook context + recent chat history
  → LLM can understand "no try something different" in context
```

**Error recovery (Debugger agent loop):**

When a DAG step fails, the Scheduler doesn't just retry blindly — it escalates to the Debugger agent for diagnosis.

```
DAG step fails (after BaseAgent's own 3 retries exhausted)
  → Scheduler sends to Debugger: error message + step context + agent output
  → Debugger analyzes, returns: {diagnosis, suggested_fix, retry_params}
  → Scheduler retries the failed step with Debugger's adjustments
  → If fails again → back to Debugger (up to 5 attempts total)
  → If Debugger can't fix after 5 tries:
    1. Record failure to Playbook as WHAT_FAILED entry (with full trace)
    2. Scheduler re-plans: skip the broken step, try alternative approach
    3. If re-plan also fails → force-stop the task
    4. Report to CEO via chat.narrative:
       "Step X failed after 5 attempts. Diagnosis: [debugger's analysis].
        I've recorded this to the playbook so I won't try this again."
```

This creates two layers of retry:
- **Low-level (BaseAgent):** 3 blind retries per agent execution
- **High-level (Scheduler + Debugger):** 5 smart retries with diagnosis and adjustment

**Race condition (CEO sends message mid-cycle):**

When the CEO sends a new message while the Scheduler is executing a plan:

```
CEO: "find momentum strategies" → OODA starts executing plan
CEO: "actually try bonds instead" → arrives mid-cycle
  → Cancel event is set → current plan stops (same mechanism as stop button)
  → Cancelled plan recorded to Playbook as INCOMPLETE
  → New message becomes the active intent
  → OODA starts fresh cycle with new goal + conversation context
  → chat.narrative: "Understood — cancelling current plan. Switching to bonds..."
```

This is the **replace** strategy: cancel current, start new. The CEO's latest intent always takes priority.

**Shared web search tool (OpenClaw/DeerFlow model):**

Any agent can search the web when it needs to. No centralized search gateway. The LLM decides on its own whether to call the search tool.

```
Shared tool: web_search (configured search provider: Brave, Tavily, DuckDuckGo, etc.)
  → Available to all agents by default
  → Policy controls which agents are allowed:
    - Allowed: researcher, miner, scheduler, ingestor, trainer
    - Denied: executor, compliance, cost_tracker (no reason to search)
  → Agent calls web_search during execute() when it needs external data
  → Results returned inline, no DAG dependency needed
```

The **Ingestor agent** still exists for heavy-duty ingestion:
- Bulk data pulls (2 years of OHLCV for S&P 500)
- Scheduled crawls (daily news scan, SEC filing monitor)
- Large-scale data pipeline operations

Lightweight searches ("what's the latest news on AAPL?", "find papers on momentum factors") happen directly from whatever agent needs them.

**Search tool implementation:**
```python
# quantclaw/agents/tools/web_search.py
async def web_search(query: str, provider: str = "auto", max_results: int = 5) -> list[dict]:
    """Search the web using the configured provider."""
    # Provider resolved from config: brave, tavily, duckduckgo, exa, etc.
    # Returns: [{title, url, snippet}, ...]
```

Registered in the shared tool pool, injected into agent execute() context. Provider configured in `quantclaw.yaml`:
```yaml
search:
  provider: duckduckgo  # free default, no API key needed
  api_key: "${SEARCH_API_KEY}"  # for Brave/Tavily/Exa
```

### Part 4: LLM Provider Support

**Ollama support in LLMRouter:**

Ollama must be a first-class provider in `LLMRouter` so the entire orchestration stack works with local models (no API keys required).

```python
# In LLMRouter
async def _call_ollama(self, model: str, messages: list[dict],
                       system: str = None, temperature: float = 0.5) -> str:
    import httpx
    ollama_url = self._config.get("ollama_url", "http://localhost:11434")
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

Config support:
```yaml
providers:
  opus:
    provider: anthropic
    model: claude-opus-4-6
  sonnet:
    provider: anthropic
    model: claude-sonnet-4-6
  gpt:
    provider: openai
    model: gpt-4o
  local:
    provider: ollama
    model: llama3.1

# Any agent can be assigned to any provider
models:
  scheduler: local  # Ollama for planning
  researcher: local
  miner: local
  backtester: local
  # ...all agents can use Ollama
```

This means the full orchestration stack (planning, narration, agent execution) works with:
- Ollama only (free, local, no API keys)
- Cloud APIs only (Anthropic, OpenAI)
- Hybrid (Ollama for cheap calls, cloud for important ones)

### Part 5: Full State Persistence

Every component survives a restart. The user comes back and everything continues where it left off — including autopilot workflows.

| Component | Storage | Mechanism |
|---|---|---|
| OODA goal | Playbook | `CEO_PREFERENCE` entry with `{goal: "..."}`, restore latest on startup |
| Autonomy mode | Playbook | `CEO_PREFERENCE` entry with `{autonomy_mode: "..."}`, restore on startup |
| Pending tasks | SQLite | Existing `tasks` table, serialize task dict to `command` column as JSON |
| Trade results | SQLite | Existing `strategy_memory` table, TrustManager reads on startup |
| Active plans | SQLite | New `plans` table (id, description, steps_json, status, created_at) |
| Event history | SQLite | Existing `events` table, batch commits every 5 seconds |
| Cycle limits | Config | `quantclaw.yaml` orchestration section |
| Cycle count | Playbook | Track cycles per goal for checkpoint enforcement |

**Autopilot restoration on restart:**

If the user was in AUTOPILOT mode with a standing goal:
1. Autopilot mode is restored from playbook
2. Standing goal is restored from playbook
3. In-progress plans are restored from SQLite (status = "executing")
4. OODA loop resumes the workflow automatically
5. Cycle count is restored — if 2 of 3 cycles were done, only 1 more before checkpoint

The user's workflow continues seamlessly. The 3-cycle limit still applies across restarts (cycle count persisted to playbook per goal).

```
Restart scenario:
  CEO set goal: "find momentum strategies" (autopilot)
  Cycle 1 completed before restart
  Server restarts
  → Restore: goal="find momentum strategies", mode=AUTOPILOT, cycles_completed=1
  → OODA resumes: cycle 2 starts
  → After cycle 3: mandatory checkpoint with CEO
```

**Playbook persistence (goal + autonomy mode):**
```
set_goal("find momentum") → playbook.add(CEO_PREFERENCE, {goal: "find momentum"})
set_mode(AUTOPILOT)        → playbook.add(CEO_PREFERENCE, {autonomy_mode: "autopilot"})
Startup                    → playbook.query(CEO_PREFERENCE) → restore latest of each
```

**Task persistence (pending tasks):**
```
ooda.add_pending_task(task_dict)  → task_store.create(agent, json.dumps(task_dict), status=pending)
ooda.act() completes             → task_store.update_status(completed)
Startup                          → task_store.list_by_status(pending) → json.loads(command) → restore
```

Note: The existing `tasks.command` column stores the full task dict as JSON string. No schema change needed.

**Trade result persistence:**
```
trust.record_trade_result(profit=100) → strategy_memory.record_result(...)
Startup                               → strategy_memory.get_stats() → restore metrics
```

**Plan persistence (new table):**
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

**Event history persistence (batch commits):**
EventBus itself has no DB reference. A persistence handler with batch commits is created inside the lifespan:
```python
# Inside lifespan, after DB is created
_event_buffer: list[Event] = []

async def buffer_event(event: Event):
    _event_buffer.append(event)

async def flush_events():
    """Flush buffered events to SQLite every 5 seconds."""
    while True:
        await asyncio.sleep(5)
        if _event_buffer:
            batch = list(_event_buffer)
            _event_buffer.clear()
            for event in batch:
                await db.conn.execute(
                    "INSERT INTO events (event_type, payload, source_agent) VALUES (?, ?, ?)",
                    (str(event.type), json.dumps(event.payload), event.source_agent)
                )
            await db.conn.commit()

bus.subscribe("*", buffer_event)
asyncio.create_task(flush_events())
```

On startup, recent events are loaded into `bus._history` for the OODA observe phase.

## Architecture After Activation

```
FastAPI Server (single process)
  |
  +-- Lifespan (creates all orchestration objects)
  |     +-- SQLite DB (WAL mode, state persistence)
  |     +-- Playbook (knowledge persistence)
  |     +-- AgentPool (all 13 agents registered)
  |     +-- Shared tools: web_search (policy-controlled per agent)
  |     +-- Dispatcher (with EventBus + cancellation token)
  |     +-- TrustManager (restored from playbook)
  |     +-- AutonomyManager (restored from playbook, including AUTOPILOT)
  |     +-- OODA Loop (background asyncio.Task, auto-restarts on crash)
  |     |     +-- Observe: EventBus + Playbook + TaskStore + Chat History
  |     |     +-- Orient: Goal + Playbook context + Conversation context (last 10 msgs)
  |     |     +-- Decide: LLM via Planner (generates DAG)
  |     |     +-- Act: Dispatcher executes DAG (cancellable)
  |     |     |     +-- Step fails → Debugger agent diagnoses (up to 5 attempts)
  |     |     |     +-- Debugger can't fix → re-plan or stop, record to Playbook
  |     |     +-- Learn: Playbook + StrategyMemory
  |     |     +-- Sleep: asyncio.Event (wakes on triggers)
  |     |     +-- Completion: DAG done = cycle done. Max 3 cycles then checkpoint.
  |     |     +-- Loop detection: vector similarity > 0.85 = stop
  |     |
  |     +-- EventBus → SQLite batch persistence (flush every 5s)
  |     +-- app.state.ooda, app.state.trust, etc. (shared references)
  |
  +-- /api/chat
  |     +-- No @agent: CEO intent → OODA loop (cancel-and-replace if mid-cycle)
  |     +-- With @agent: direct LLM chat (existing behavior)
  |
  +-- /api/orchestration/stop → Stop button (cancels current workflow)
  +-- /api/orchestration/* → control endpoints (use app.state, not module-level)
  +-- /ws/events → WebSocket broadcast (floor + chat narrative)
  +-- All existing endpoints unchanged
```

## Frontend Changes

**Chat panel — new `useChatStream` hook:**
The chat panel needs to listen for `chat.narrative` WebSocket events and append them as assistant messages. Currently the chat sends POST and waits for response. With orchestration:

```typescript
// useChatStream.ts
// Subscribes to WebSocket, listens for chat.narrative events
// Appends each narrative message to the chat message list
// Recognizes orchestration.cycle_complete as "Scheduler is done talking"

// Chat component flow:
// 1. User sends message → POST /api/chat
// 2. Response has status: "orchestrating" → show typing indicator
// 3. WebSocket chat.narrative arrives → append to messages, keep typing indicator
// 4. More chat.narrative events → keep appending
// 5. orchestration.cycle_complete → remove typing indicator, cycle done
```

**Stop button:**
Add a stop button to the chat panel (visible when `status === "orchestrating"`). Calls `POST /api/orchestration/stop`. Similar to Claude Code / Cursor stop buttons.

**Floor rendering** — already handles all orchestration events from previous implementation. No changes needed.

## Graceful Shutdown

```python
# In lifespan teardown
ooda_task.cancel()
event_flush_task.cancel()
try:
    await ooda_task
    await event_flush_task
except asyncio.CancelledError:
    pass
# Final flush of buffered events
if _event_buffer:
    # ... flush remaining events
await db.close()
```

## Background Task Crash Recovery

```python
# The OODA background task wrapper
async def _ooda_background(ooda: OODALoop, bus: EventBus):
    while True:
        try:
            await ooda.run_continuous()
        except asyncio.CancelledError:
            break  # Graceful shutdown
        except Exception as e:
            # Log error, notify CEO, restart
            await bus.publish(Event(
                type=EventType.CHAT_NARRATIVE,
                payload={"message": f"Scheduler encountered an error and is restarting: {e}",
                         "role": "scheduler"},
                source_agent="scheduler",
            ))
            await asyncio.sleep(5)  # Brief pause before restart
```

## What Changes

| File | Change |
|---|---|
| `quantclaw/dashboard/api.py` | Move orchestration objects into lifespan → `app.state`. Update all `/api/orchestration/*` endpoints to use `request.app.state`. Modify `/api/chat` to route through OODA when no @agent prefix, pass last 10 chat messages. Handle cancel-and-replace for mid-cycle messages. Add `/api/orchestration/stop` endpoint. |
| `quantclaw/orchestration/ooda.py` | Add `run_cycle()` for single-shot. Add `run_continuous()` for background task with crash recovery. Add goal/mode persistence via playbook. Add cycle limits (3 cycles, 20 min timeout). Add loop detection (vector similarity). Add conversation context parameter. Add cancel support. Add Debugger agent escalation on step failure. Add cycle count persistence for autopilot restoration. |
| `quantclaw/orchestration/trust.py` | Load trade history from StrategyMemory on startup. |
| `quantclaw/orchestration/autonomy.py` | Add playbook persistence for mode changes. |
| `quantclaw/orchestrator/router.py` | Add Ollama provider support (`_call_ollama`). |
| `quantclaw/orchestrator/dispatcher.py` | Add cancellation token (`asyncio.Event`). Check cancel between steps. Wrap agent tasks as cancellable. |
| `quantclaw/state/db.py` | Add `plans` table to schema. Enable WAL mode. |
| `quantclaw/orchestrator/planner.py` | Persist plans to SQLite `plans` table. |
| `quantclaw/events/types.py` | Add `CHAT_NARRATIVE` and `ORCHESTRATION_CYCLE_COMPLETE` event types. |
| `quantclaw/config/default.yaml` | Add `orchestration:` section with cycle limits. Add `ollama` provider. Add `search:` section. |
| Create: `quantclaw/agents/tools/web_search.py` | Shared web search tool with pluggable providers (DuckDuckGo free default). |
| `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts` | Handle `chat.narrative` and `orchestration.cycle_complete` events. |
| Create: `quantclaw/dashboard/app/app/dashboard/chat/useChatStream.ts` | New hook: subscribe to WebSocket for `chat.narrative` events, append to chat messages. |

## Non-Changes

- `quantclaw/daemon.py` — still exists for standalone daemon use, but not started by default
- All existing API endpoints (except /api/chat) — unchanged, backward compatible
- Direct @agent chat — bypasses orchestration, works as before
- `quantclaw/events/bus.py` — no changes; persistence handler subscribed externally in lifespan
- Frontend floor rendering — already handles orchestration events from previous implementation
