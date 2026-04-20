# Workflow Efficiency — Design Document

**Date:** 2026-04-06
**Status:** Approved (v2 — audit fixes)
**Author:** Harry + Claude
**Inspired by:** oh-my-codex (state machine phases, role routing), DeerFlow (middleware guards), OpenClaw (push-based announce)
**Related:** [Miner & Trainer](2026-04-06-miner-trainer-design.md), [Scheduler Intelligence](2026-04-06-scheduler-intelligence-design.md)

## Problem

The current orchestration makes an LLM call for every decision: planning, per-agent execution, evaluation, narration. Most of these calls are unnecessary — Backtester, Ingestor, Trainer, Compliance, and Cost Tracker are mechanical agents that don't need LLM reasoning. And common workflows (factor discovery, backtesting) follow predictable patterns that don't need LLM planning.

## Principle

**Minimize the number of LLM calls, not the model quality.** All LLM calls use the most capable configured model. The savings come from calling the LLM only when creative reasoning is needed — everything else is code-only.

## Part 1: LLM Call Elimination

### Which agents need LLM calls

| Agent | LLM call? | Why |
|---|---|---|
| Miner | **Yes** | Hypothesis generation is creative |
| Researcher | **Yes** | Synthesizing search results requires reasoning |
| Reporter | **Yes** | Summarization needs reasoning |
| Scheduler/Planner | **Only for novel requests** | Template match handles known workflows |
| Evaluation | **Only for ambiguous cases** | Heuristic handles clear results |
| Trainer | **No** | Code-only pipeline: Scheduler/Researcher decide model type + params, Trainer executes mechanically in sandbox |
| Backtester | **No** | Runs strategy in sandbox, returns numbers |
| Ingestor | **No** | Fetches data via API |
| Risk Monitor | **No** | Rule checking, arithmetic |
| Compliance | **No** | Rule checking |
| Cost Tracker | **No** | Arithmetic |
| Sentinel | **No** | Monitoring, alerting |
| Executor | **No** | Submits orders via broker API |
| Debugger | **Yes** | Diagnosis requires reasoning |
| Narration | **No** | Format results programmatically |

### Cost comparison

```
Current (all LLM):
  Planning LLM call                         ~2K tokens
  5 agent LLM calls                         ~7.5K tokens
  Evaluation LLM call                       ~1K tokens
  Narration LLM call                        ~500 tokens
  Total per iteration: ~11K tokens
  3 iterations: ~33K tokens

Optimized (selective LLM):
  Planning: template match (0) or 1 LLM call if novel (~2K)
  Miner LLM call                            ~1.5K tokens
  Researcher LLM call                       ~1.5K tokens
  Trainer/Backtester/Ingestor               0 tokens (code-only)
  Evaluation: heuristic (0) or LLM if ambiguous (~1K)
  Narration: programmatic                   0 tokens
  Total per iteration: ~3-6K tokens
  3 iterations: ~9-18K tokens

  Savings: ~50-75% fewer tokens
```

### Implementation

Code-only agents skip the LLM router entirely. Their `execute()` method does its work directly:

```python
class BacktesterAgent(BaseAgent):
    name = "backtester"
    model = "opus"  # only used if agent needs LLM (it doesn't)
    
    async def execute(self, task: dict) -> AgentResult:
        # No LLM call — runs strategy in sandbox directly
        sandbox = Sandbox(config=self._config)
        result = await sandbox.execute_strategy(...)
        return AgentResult(status=AgentStatus.SUCCESS, data=result)
```

LLM-calling agents use the router:

```python
class MinerAgent(BaseAgent):
    name = "miner"
    
    async def execute(self, task: dict) -> AgentResult:
        # Needs LLM for creative hypothesis generation
        from quantclaw.orchestrator.router import LLMRouter
        router = LLMRouter(self._config)
        response = await router.call("miner", messages=[...], system=MINER_PROMPT)
        # ... process response, run code in sandbox
```

## Part 2: Workflow Templates

Common workflows follow predictable patterns. Instead of calling the Planner LLM to generate a DAG from scratch, match the request against known templates.

### Template matching (code-only, no LLM)

```python
WORKFLOW_TEMPLATES = {
    "factor_discovery": {
        "match": ["factor", "alpha", "signal", "find.*strateg", "discover"],
        "phases": [
            {"agent": "researcher", "task": "search_approaches", "needs_llm": True},
            {"agent": "ingestor", "task": "fetch_data", "needs_llm": False, "parallel_with": 0},
            {"agent": "miner", "task": "discover_factors", "needs_llm": True, "depends": [0, 1]},
            {"agent": "trainer", "task": "train_model", "needs_llm": False, "depends": [2]},
            {"agent": "backtester", "task": "evaluate", "needs_llm": False, "depends": [3]},
        ],
        "max_iterations": 3,
    },
    "strategy_backtest": {
        "match": ["backtest", "test.*strateg", "evaluate.*strateg"],
        "phases": [
            {"agent": "ingestor", "task": "fetch_data", "needs_llm": False},
            {"agent": "backtester", "task": "evaluate", "needs_llm": False, "depends": [0]},
            {"agent": "reporter", "task": "summarize", "needs_llm": True, "depends": [1]},
        ],
        "max_iterations": 1,
    },
    "market_research": {
        "match": ["research", "analyze.*market", "what.*happening", "news"],
        "phases": [
            {"agent": "researcher", "task": "search", "needs_llm": True},
            {"agent": "reporter", "task": "summarize", "needs_llm": True, "depends": [0]},
        ],
        "max_iterations": 0,
    },
    "risk_check": {
        "match": ["risk", "exposure", "drawdown", "portfolio.*check"],
        "phases": [
            {"agent": "risk_monitor", "task": "check_risk", "needs_llm": False},
            {"agent": "compliance", "task": "check_rules", "needs_llm": False, "parallel_with": 0},
            {"agent": "reporter", "task": "summarize", "needs_llm": True, "depends": [0, 1]},
        ],
        "max_iterations": 0,
    },
    "model_training": {
        "match": ["train.*model", "ml.*pipeline", "machine.*learn"],
        "phases": [
            {"agent": "researcher", "task": "search_models", "needs_llm": True},
            {"agent": "ingestor", "task": "fetch_data", "needs_llm": False, "parallel_with": 0},
            {"agent": "trainer", "task": "train_model", "needs_llm": False, "depends": [0, 1]},
            {"agent": "backtester", "task": "evaluate", "needs_llm": False, "depends": [2]},
        ],
        "max_iterations": 3,
    },
    "go_live": {
        "match": ["paper.*trade", "live.*trade", "go.*live", "deploy"],
        "phases": [
            {"agent": "compliance", "task": "check_rules", "needs_llm": False},
            {"agent": "risk_monitor", "task": "check_risk", "needs_llm": False, "parallel_with": 0},
            {"agent": "executor", "task": "submit_orders", "needs_llm": False, "depends": [0, 1]},
            {"agent": "reporter", "task": "confirm", "needs_llm": True, "depends": [2]},
        ],
        "max_iterations": 0,
    },
    "refine_factors": {
        "match": ["refine.*factor", "improve.*factor", "better.*factor", "tweak"],
        "phases": [
            {"agent": "miner", "task": "refine_factors", "needs_llm": True},
            {"agent": "trainer", "task": "train_model", "needs_llm": False, "depends": [0]},
            {"agent": "backtester", "task": "evaluate", "needs_llm": False, "depends": [1]},
        ],
        "max_iterations": 3,
    },
    "apply_new_model": {
        "match": ["try.*model", "different.*model", "switch.*model", "compare.*model"],
        "phases": [
            {"agent": "researcher", "task": "search_models", "needs_llm": True},
            {"agent": "trainer", "task": "train_model", "needs_llm": False, "depends": [0]},
            {"agent": "backtester", "task": "evaluate", "needs_llm": False, "depends": [1]},
        ],
        "max_iterations": 3,
    },
}
```

### Matching logic

```python
import re

def match_workflow(message: str) -> dict | None:
    """Match a CEO message to a workflow template. Code-only, no LLM."""
    lower = message.lower()
    for name, template in WORKFLOW_TEMPLATES.items():
        if any(re.search(pattern, lower) for pattern in template["match"]):
            return {"name": name, **template}
    return None  # No match → fall through to Planner LLM
```

### Integration with OODA decide()

```python
async def decide(self, orientation: dict) -> Plan | None:
    # Try template match first (free, no LLM call)
    goal = orientation.get("goal", "")
    template = match_workflow(goal)
    
    if template:
        # Build plan from template (code-only)
        plan = self._plan_from_template(template, orientation)
    else:
        # Novel request → Planner LLM generates custom DAG
        plan = await planner.create_plan(request, context=...)
    
    # ... rest of decide logic unchanged
```

### Templates are starting points, not constraints

The Scheduler still has full creative latitude:
- Templates handle the common 80% of requests without LLM cost
- Novel/ambiguous requests go through the Planner LLM
- After the first iteration, the Scheduler may generate a custom DAG for refinement regardless of template match
- Templates can be extended via config without code changes

## Part 3: Heuristic-First Evaluation

The current `_evaluate_results()` calls the LLM every time. Most evaluations are obvious from the numbers:

```python
async def _evaluate_results(self, results: dict, iteration: int) -> dict:
    best_sharpe = ...  # extract from results
    max_iterations = ...
    
    # Heuristic (code-only, no LLM)
    if iteration >= max_iterations:
        verdict = "pursue" if best_sharpe > 0 else "abandon"
        return {"verdict": verdict, "reasoning": f"Final iteration. Sharpe: {best_sharpe:.2f}"}
    
    if best_sharpe > 1.5:
        return {"verdict": "pursue", "reasoning": f"Strong result: Sharpe {best_sharpe:.2f}"}
    
    if best_sharpe < 0:
        return {"verdict": "abandon", "reasoning": f"Negative Sharpe: {best_sharpe:.2f}"}
    
    # Ambiguous range (0.0 - 1.5) → ask LLM
    return await self._llm_evaluate(results, iteration)
```

This eliminates the LLM call for ~60% of evaluations (clearly good or clearly bad results).

## Part 4: Programmatic Narration

Instead of calling the LLM to summarize each step, format results programmatically:

```python
def _narrate_step(self, agent: str, result: AgentResult) -> str:
    """Format step result as narrative text. No LLM call."""
    data = result.data
    
    if agent == "backtester" and "sharpe" in data:
        return f"Backtest complete: Sharpe {data['sharpe']:.2f}, annual return {data.get('annual_return', 0):.1%}, max drawdown {data.get('max_drawdown', 0):.1%}"
    
    if agent == "miner" and "factors" in data:
        n = len(data["factors"])
        best = max((f.get("metrics", {}).get("sharpe", 0) for f in data["factors"]), default=0)
        return f"Discovered {n} factors. Best Sharpe: {best:.2f}"
    
    if agent == "trainer" and "model_type" in data:
        return f"Trained {data['model_type']} model. Test Sharpe: {data.get('sharpe', 0):.2f}, overfit ratio: {data.get('metrics', {}).get('overfit_ratio', 0):.2f}"
    
    if agent == "researcher" and "findings" in data:
        n = len(data["findings"])
        return f"Found {n} relevant findings"
    
    if agent == "ingestor" and "ohlcv" in data:
        n = len(data["ohlcv"])
        return f"Fetched data for {n} symbols"
    
    # Fallback
    return f"{agent} completed"
```

The Reporter agent still uses LLM for final summaries — that's valuable. But per-step narration is mechanical formatting.

## Configuration

```yaml
orchestration:
  # ... existing config ...
  workflow_templates: true   # enable template matching (default: true)
  heuristic_evaluation: true # heuristic-first evaluation (default: true)
  programmatic_narration: true # code-based narration (default: true)
  llm_evaluation_range: [0.0, 1.5]  # Sharpe range that triggers LLM evaluation
```

## What Changes

| File | Change |
|---|---|
| Create: `quantclaw/orchestration/workflows.py` | Workflow templates + match_workflow() |
| Create: `quantclaw/orchestration/narration.py` | Programmatic narration formatter |
| Modify: `quantclaw/orchestration/ooda.py` | Use templates in decide(), heuristic-first evaluation, programmatic narration |
| Modify: `quantclaw/config/default.yaml` | Add workflow efficiency config |
| Create: `tests/test_workflows.py` | Template matching tests |
| Create: `tests/test_narration.py` | Narration formatting tests |

## Non-Changes

- Agent implementations — unchanged, they already work as code-only or LLM-calling
- LLMRouter — unchanged, still routes all LLM calls to best configured model
- Sandbox — unchanged
- EventBus — unchanged
- Frontend — unchanged
