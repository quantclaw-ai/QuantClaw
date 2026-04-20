# Heartbeat

The OODA loop is QuantClaw's heartbeat. It runs continuously, waking on events, planning work, executing agents, and learning from results.

## OODA Phases

```
OBSERVE -> ORIENT -> DECIDE -> ACT -> LEARN -> SLEEP
   ^                                              |
   |______________________________________________|
```

### 1. OBSERVE
Gather current state:
- Pending tasks and events from EventBus
- Recent Playbook entries (last 20)
- Current trust level and autonomy mode
- Active agent statuses

### 2. ORIENT
Determine what to do:
- Process pending tasks (chat input, scheduled jobs)
- Respond to market events (gaps, regime changes)
- Align actions toward the current goal
- Check if iteration is needed on previous cycle

### 3. DECIDE
Generate a plan:
1. **Template match first** -- common workflows (signal_hunting, ml_pipeline, etc.) resolve without an LLM call
2. **LLM Planner fallback** -- Planner generates a DAG with agent assignments, task dicts, and dependency edges
3. **Approval gate** -- Autopilot auto-approves; Plan mode waits for CEO; chat-triggered cycles auto-approve

Output: `Plan` object with ordered `PlanStep` nodes.

### 4. ACT
Execute the plan via Dispatcher:
- Steps with no dependencies run in parallel
- Each step's result is injected into dependents as `_upstream_results`
- Failed steps don't block independent branches
- Narration events broadcast progress to the dashboard

### 5. LEARN
Record results to Playbook:
- Strategy results with Sharpe/returns metrics
- What failed and why
- Factor library updates
- Agent performance data

### 6. SLEEP
Wait for the next trigger:
- EventBus events (market, agent, schedule)
- Chat input from CEO
- Cron schedule firing
- OODA interval timer (default 30s)

## Iteration Loop

After ACT, the evaluator checks results:

```
Result -> Evaluate (LLM) -> pursue: break, record success
                          -> iterate: refine, re-DECIDE with context
                          -> abandon: break, record failure
```

- Max iterations per cycle: 3
- Temperature shifts toward exploit on iteration
- Loop similarity detection prevents spinning (threshold 0.85)

## Event Types

| Category | Events |
|----------|--------|
| Market | `gap_detected`, `regime_change` |
| Trade | `order_submitted`, `order_filled`, `reconciliation_fail` |
| Pipeline | `ingestion_done`, `ingestion_failed`, `backtest_done` |
| Factor | `decay_detected`, `mining_complete` |
| Agent | `task_started`, `task_completed`, `task_failed` |
| Orchestration | `plan_created`, `step_started/completed/failed`, `cycle_complete`, `evaluation` |
| System | `schedule.triggered`, `cost.budget_warning`, `trust.level_changed` |

## Lifecycle

```
startup (FastAPI lifespan)
  -> restore Playbook, Trust, Autonomy from disk
  -> start EventBus
  -> start OODA loop
  -> start daemon scheduler
  -> serve dashboard + API

shutdown
  -> drain pending events
  -> stop OODA loop
  -> flush Playbook
```
