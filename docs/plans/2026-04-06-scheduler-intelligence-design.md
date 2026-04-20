# Scheduler Intelligence — Design Document

**Date:** 2026-04-06
**Status:** Approved (v3 — cross-doc audit fixes)
**Author:** Harry + Claude
**Related:** [Miner & Trainer](2026-04-06-miner-trainer-design.md), [Workflow Efficiency](2026-04-06-workflow-efficiency-design.md)

## Problem

The Scheduler generates one plan per goal, executes it, and stops. It doesn't evaluate whether results are good or bad, doesn't iterate on failures, doesn't learn from the Playbook to avoid repeating mistakes, and doesn't balance exploration of new ideas vs. exploitation of proven approaches. Event payloads are thin — no reasoning traces for debugging or auditing.

## Solution

Enhance the existing OODA loop with iterative intelligence: result evaluation, explore/exploit temperature control, LLM-judged iteration decisions, full chat narration, enriched event payloads, and a dashboard Log page.

## Part 1: Iterative OODA Enhancement

The existing `run_cycle()` gains a new `_evaluate_results()` step between Act and Learn:

```
run_cycle() enhanced:
  observe → orient → decide → act → EVALUATE → learn → sleep
                                        ↓
                              "Results good enough?"
                              pursue  → summarize, record success, done
                              iterate → feed suggestion into next decide(), loop back
                              abandon → record WHAT_FAILED, try different approach
                              (bounded by max_iterations_per_cycle: 3)
```

**Two separate limits:**
- `max_cycles_per_goal: 3` — how many times `run_cycle()` is called (in autopilot). Counts top-level cycles.
- `max_iterations_per_cycle: 3` — how many times the evaluate → decide → act loop repeats *within* a single `run_cycle()` call. After 3 iterations, force `pursue` with the best result so far.

New method `_evaluate_results()` added to OODALoop:
- Step 1: Compares results against Playbook percentile ranking (quantitative). If Playbook has < 3 strategy results, skip percentile and tell the LLM: "Not enough history for comparison. Evaluate on absolute metrics."
- Step 2: Feeds results + Playbook context + percentile to Scheduler LLM (temp 0.2) for judgment
- LLM returns: `{verdict: "pursue" | "iterate" | "abandon", reasoning: str, suggestion: str}`
- Emits `orchestration.evaluation` event with verdict and reasoning (visible in chat + Log page)

The verdict drives the next action:
- **pursue** → record to Playbook as STRATEGY_RESULT, report to CEO, cycle done
- **iterate** → feed LLM's suggestion + previous results into next `decide()` via `_iteration_context`, loop back to decide
- **abandon** → record to Playbook as WHAT_FAILED with full trace, try different approach or stop

**Iteration context accumulator:**

`_iteration_context` is a list that accumulates within a single `run_cycle()` call:

```python
_iteration_context: list[dict] = []

# After each iteration:
_iteration_context.append({
    "iteration": 1,
    "plan_summary": "Tested momentum 5d",
    "results": {"sharpe": 0.3},
    "verdict": "iterate",
    "suggestion": "Try adding volatility filter",
})
```

This context is injected into the Planner prompt on the next iteration so the LLM knows what's been tried and what was suggested.

**LLM calls tracking:**

Each cycle tracks its internal LLM call count. Included in the `orchestration.cycle_complete` event:

```python
{"llm_calls": 6,  # 2 per iteration (plan + evaluate) × 3 iterations
 "iterations": 3}
```

## Part 2: Explore/Exploit Temperature

Adaptive exploration based on Playbook maturity, with LLM override per-iteration.

**Default mode based on Playbook size:**

| Playbook entries | Default mode | Temperature | Behavior |
|---|---|---|---|
| 0-4 | explore | 0.7 | Not enough data, try new things |
| 5-14 | balanced | 0.4 | Some data, mix of new and refinement |
| 15+ | exploit | 0.2 | Rich playbook, refine what works |

**LLM override (per-iteration, not just per-cycle):**

The mode is determined at cycle start based on Playbook size. But the LLM can override it on any iteration. For example:

```
Iteration 1 (explore, temp 0.7): tries volatility approach → Sharpe 0.8
Iteration 2: LLM says "promising, switch to exploit to refine" → temp 0.2
Iteration 3 (exploit, temp 0.2): refines volatility + momentum → Sharpe 1.4
```

The override is included in the Planner prompt:

```
"Current mode: exploit (temp 0.2). Playbook has 50 entries, mostly momentum variants.
You may override to explore if you believe a fundamentally different approach is needed.
Respond with exploration_mode: explore | exploit | balanced"
```

The override is recorded in the event payload for CEO visibility.

**Configuration:**
```yaml
orchestration:
  exploration:
    explore_temp: 0.7
    exploit_temp: 0.2
    balanced_temp: 0.4
    high_explore_until: 5
    balanced_until: 15
  max_iterations_per_cycle: 3
```

## Part 3: Result Evaluation (Quantitative + LLM)

When a cycle's DAG completes, results are evaluated in two steps:

**Step 1 — Playbook percentile ranking:**

```python
past_results = await playbook.query(entry_type=STRATEGY_RESULT)
past_sharpes = [e.content.get("sharpe", 0) for e in past_results]

if len(past_sharpes) < 3:
    percentile = None  # Not enough history
    percentile_note = "Not enough history for comparison. Evaluate on absolute metrics."
else:
    percentile = sum(1 for s in past_sharpes if current_sharpe > s) / len(past_sharpes)
    percentile_note = f"Top {(1 - percentile) * 100:.0f}% of {len(past_sharpes)} past strategies"
```

**Step 2 — LLM judgment:**

```
Scheduler LLM (temp 0.2, precise judgment):

"You are evaluating strategy results.

Result: Sharpe 1.2, annual return 18%, max drawdown -8%
{percentile_note}
Playbook context: 3 similar momentum strategies tried, best was Sharpe 0.9
Previous iterations this cycle: [list of _iteration_context entries]
Iteration {n} of {max_iterations_per_cycle}

Should we:
- pursue: results are strong enough to act on
- iterate: promising but could improve, suggest refinement
- abandon: not worth continuing, try something different

If this is the last iteration, you MUST choose pursue or abandon.

Respond as JSON: {verdict, reasoning, suggestion}"
```

Emits `orchestration.evaluation` event:
```python
{"plan_id": "abc", "iteration": 2, "verdict": "iterate",
 "percentile": 0.85, "reasoning": "Good but room for improvement",
 "suggestion": "Try 20d lookback instead of 10d"}
```

## Part 4: Chat Narration + Enriched Events

Full real-time narration in chat (via existing `chat.narrative` WebSocket), plus summary at the end.

**Narration example:**
```
Cycle 1, Iteration 1 (explore, temp 0.7):
  "Starting exploration. Playbook has 3 entries — trying something new."
  "Plan: Research volatility patterns → Generate factor → Backtest"
  [agents execute, floor lights up]
  [orchestration.evaluation event]
  "Results: Sharpe 0.4, not enough history for comparison. Iterating — suggest adding momentum filter."

Cycle 1, Iteration 2 (exploit, temp 0.2):
  "Refining: volatility + momentum hybrid"
  [agents execute]
  [orchestration.evaluation event]
  "Results: Sharpe 1.1, top 20%. Promising! One more refinement."

Cycle 1, Iteration 3 (exploit, temp 0.2):
  "Fine-tuning lookback window from 10d to 20d"
  [agents execute]
  [orchestration.evaluation event]
  "Results: Sharpe 1.4, top 8% of all strategies."

Summary:
  "Explored 3 iterations. Best: vol-momentum hybrid (Sharpe 1.4, top 8%).
   6 LLM calls used. Recorded to Playbook. Want me to paper trade it?"
```

**Enriched event payloads — every event carries reasoning context:**

```python
# orchestration.plan_created
{"plan_id": "abc", "steps": 3, "goal": "find alpha",
 "reasoning": "Playbook momentum strategies underperforming. Trying volatility.",
 "exploration_mode": "explore", "temperature": 0.7,
 "playbook_entries_consulted": 3, "cycle": 1, "iteration": 1}

# orchestration.evaluation (NEW event type)
{"plan_id": "abc", "iteration": 2, "verdict": "iterate",
 "percentile": 0.85, "results": {"sharpe": 1.1},
 "reasoning": "Good but room for improvement",
 "suggestion": "Try 20d lookback instead of 10d"}

# agent.task_completed (enriched)
{"agent": "backtester", "plan_id": "abc", "step_id": 2,
 "result_summary": {"sharpe": 1.4, "annual_return": 0.22, "max_drawdown": -0.08},
 "reasoning": "Backtest completed successfully"}

# orchestration.cycle_complete (enriched)
{"plan_id": "abc", "verdict": "pursue", "percentile": 0.92,
 "reasoning": "Top 8% result, significantly better than previous attempts",
 "suggestion": "Ready for paper trading", "cycle": 1,
 "iterations": 3, "llm_calls": 6,
 "exploration_mode": "exploit", "temperature": 0.2}
```

All persisted to SQLite via existing EventPersister. Queryable on the Log page.

**Implementation notes for enriched events:**
- `reasoning` field must be included in `orchestration.plan_created` (currently missing in ooda.py)
- `playbook_entries_consulted` count must be tracked and included
- `_llm_call_count` must be incremented in BOTH `decide()` (Planner call) AND `_evaluate_results()` (evaluation call) — currently only incremented in evaluation
- `_iteration_context` must capture full agent metrics (IC, Rank IC, turnover, Sharpe) not just Sharpe — so the Planner prompt has full context for refinement decisions

**Exploration mode override (future enhancement):**
The Planner prompt asks the LLM to respond with `exploration_mode: explore|exploit|balanced`. Currently this is not parsed from the Planner response — the override only works via the evaluation verdict ("iterate → switch to exploit"). Parsing the override from Planner response is deferred as a future enhancement since the evaluation-based mode switch already provides this capability.

## Part 5: Dashboard Log Page

**NOTE:** The Log page has already been implemented (see commit `c2b00dd`). The design below documents what was built.

New page at `/dashboard/logs` — sidebar item between Agents and Risk.

**Layout:**
```
+----------------------------------------------------------+
| Logs                                             [Filter] |
|                                                           |
| Filter: [All Events v] [All Agents v] [Today v]          |
|                                                           |
| 14:32:05  scheduler   orchestration.plan_created          |
|   Goal: "find alpha"                                      |
|   Mode: explore (temp 0.7) | Iteration 1                 |
|   Reasoning: "Playbook has 3 entries, exploring"          |
|   Steps: researcher > miner > backtester                  |
|                                                           |
| 14:32:08  researcher  agent.task_started                  |
|   Task: "Research volatility patterns"                    |
|                                                           |
| 14:32:15  researcher  agent.task_completed                |
|   Found 3 promising approaches                            |
|                                                           |
| 14:33:01  backtester  agent.task_completed                |
|   Sharpe: 1.4, Annual: 22%, Drawdown: -8%                |
|                                                           |
| 14:33:02  scheduler   orchestration.evaluation            |
|   Verdict: pursue (top 8%)                                |
|   Reasoning: "Significantly better than previous"         |
|                                                           |
| 14:33:03  scheduler   orchestration.cycle_complete        |
|   3 iterations, 6 LLM calls                               |
+----------------------------------------------------------+
```

**Filters:**
- Event type: All, orchestration.*, agent.*, chat.*, market.*, trade.*
- Agent: All, scheduler, researcher, backtester, etc.
- Time range: Today, Last 24h, Last 7d, All

**Auto-refresh:** Polls every 5 seconds when the page is active via `setInterval` + fetch. No new WebSocket needed.

**API changes:** Extend `GET /api/events` with query params:
```
GET /api/events?limit=100&offset=0&agent=scheduler&type=orchestration.*&since=2026-04-06
```

SQL mapping: `type=orchestration.*` → `WHERE event_type LIKE 'orchestration.%'`

**Frontend:** New page component at `app/dashboard/logs/page.tsx` + sidebar nav item.

## Configuration (Complete)

```yaml
orchestration:
  max_cycles_per_goal: 3
  max_iterations_per_cycle: 3
  cycle_timeout_minutes: 20
  ooda_interval: 30
  max_chat_history: 10
  max_debugger_retries: 5
  loop_similarity_threshold: 0.85
  exploration:
    explore_temp: 0.7
    exploit_temp: 0.2
    balanced_temp: 0.4
    high_explore_until: 5
    balanced_until: 15
```

## What Changes

| File | Change |
|---|---|
| `quantclaw/orchestration/ooda.py` | Add `_evaluate_results()`, `_get_exploration_mode()`, `_iteration_context`. Enhance `run_cycle()` with evaluate-iterate loop (max 3 iterations). Enrich all event payloads with reasoning, iteration count, LLM call count. |
| `quantclaw/orchestrator/planner.py` | Enrich Planner system prompt with Playbook context, iteration context, explore/exploit mode. Accept temperature parameter per-call. |
| `quantclaw/events/types.py` | Add `ORCHESTRATION_EVALUATION` event type. |
| `quantclaw/config/default.yaml` | Add `orchestration.exploration` and `max_iterations_per_cycle` config. |
| `quantclaw/dashboard/api.py` | Extend `GET /api/events` with filter query params (agent, type, since, limit, offset). SQL LIKE pattern matching. |
| `quantclaw/dashboard/app/app/dashboard/logs/page.tsx` | New Log page component with filters, event list, and 5-second auto-refresh. |
| `quantclaw/dashboard/app/app/dashboard/layout.tsx` | Add Logs to sidebar navigation between Agents and Risk. |
| `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts` | Handle `orchestration.evaluation` event (show verdict on scheduler). |

## Non-Changes

- EventBus — no changes, payloads are just richer dicts
- EventPersister — no changes, already persists all payloads as JSON
- SQLite schema — no changes, events table already stores JSON payloads
- Existing orchestration endpoints — unchanged
- Frontend floor rendering — unchanged (except new event type handler)
