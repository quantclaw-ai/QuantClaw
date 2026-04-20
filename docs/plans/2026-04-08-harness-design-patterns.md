# Harness Design Patterns for QuantClaw

Inspired by [Anthropic's harness design article](https://www.anthropic.com/engineering/harness-design-long-running-apps). Five architectural patterns to move QuantClaw from "pipeline that runs" to "system that autonomously finds real alpha."

## Problem Statement

The current pipeline runs end-to-end (Researcher -> Ingestor -> Miner -> Trainer -> Backtester -> Reporter) but has structural blind spots:

- The evaluator trusts self-reported metrics (Trainer says Sharpe 28, evaluator pursues it)
- No upfront agreement on what "success" looks like
- OODA iterations pollute context with prior failures, anchoring the LLM
- No feedback loop to improve the evaluator's judgment over time
- Unknown which scaffolding components are still necessary

## Pattern 1: Independent Evaluator Agent

### What

A new `evaluator` agent that independently backtests strategies on a **held-out time window** (last 3-4 months of the requested date range). It receives `strategy_code` from the Trainer, runs its own sandbox backtest on data the Trainer never saw, and produces the real verdict.

### Why

The article says "agents tend to confidently praise their own work." The Trainer and pipeline Backtester are both part of the same DAG — they're the "generator" side. The Evaluator is architecturally separate: it wasn't part of the plan, uses different data, and is incentivized to catch problems.

### How

**Data splitting:**
- If the pipeline uses `2023-01-01` to `2024-12-31`, the Trainer trains on `2023-01-01` to `2024-08-31`
- The pipeline Backtester validates on the same range (in-sample check)
- The Evaluator backtests on `2024-09-01` to `2024-12-31` (held-out, never seen by Trainer)

**DAG position:**
```
Researcher + Ingestor -> Miner -> Trainer -> Backtester -> Evaluator -> Reporter
                                                              |
                                                    (held-out backtest)
```

**Verdict logic:**
- The Evaluator compares in-sample Sharpe (from Backtester) vs held-out Sharpe (its own)
- If held-out Sharpe < 50% of in-sample Sharpe: `overfit`
- If held-out Sharpe < 0: `no_edge`
- If held-out Sharpe > 0 and passes contract thresholds: `validated`
- The OODA evaluator reads the Evaluator agent's output, not the Trainer's

**Agent spec:**
```python
AgentSpec(
    name="evaluator",
    description="Independent out-of-sample validation on held-out data",
    uses_llm=False,
    daemon=False,
    inputs=["strategy_code (from upstream trainer)", "symbols", "full_date_range"],
    outputs=["held_out_sharpe", "held_out_return", "held_out_drawdown",
             "degradation_ratio", "verdict"],
    depends_on=["backtester"],
    feeds_into=["reporter"],
)
```

### Key Decision

The held-out window is the **last 3-4 months** of the requested date range. The Trainer's `end` date gets shifted back by 3 months, and the Evaluator gets the original `end` date. This means the Planner doesn't need to know about the split — the Evaluator agent handles it internally.


## Pattern 2: Sprint Contracts

### What

Before a DAG executes, the Planner emits a **contract** alongside the plan — explicit, measurable success criteria that the Evaluator checks against.

### Why

Currently agents run blind. The Miner doesn't know what Sharpe the evaluator will accept. The Trainer doesn't know what overfit ratio triggers abandon. The evaluator decides after the fact using ad-hoc LLM judgment. The contract makes "done" unambiguous before work starts.

### How

**Config hard floors** (in `quantclaw.yaml`):
```yaml
contracts:
  min_sharpe: 0.0          # Absolute floor — never pursue negative
  max_overfit_ratio: 3.0    # Absolute ceiling
  min_sample_size: 200      # Minimum data points
  min_trades: 10            # Minimum trades in backtest
  min_held_out_sharpe: 0.0  # Must be positive out-of-sample
```

**Planner-generated per-cycle thresholds** (tightened based on Playbook):
```json
{
  "target_sharpe": 0.8,
  "max_overfit_ratio": 2.0,
  "min_held_out_sharpe": 0.3,
  "rationale": "Playbook has 12 entries, best Sharpe is 1.2, targeting top quartile"
}
```

**Contract flow:**
1. Planner reads Playbook, generates contract alongside DAG
2. Contract travels as metadata on the Plan object
3. Evaluator agent receives contract, checks held-out results against it
4. OODA evaluator reads Evaluator verdict — no more ad-hoc LLM judgment for the pursue/iterate/abandon decision

**Contract in Plan:**
```python
@dataclass
class Plan:
    id: str
    description: str
    steps: list[PlanStep]
    contract: dict = field(default_factory=dict)  # NEW
```

### Key Decision

The Planner sets thresholds via LLM based on Playbook context. Config only sets hard floors that can never be relaxed. This means the bar rises naturally as the Playbook fills with better results.


## Pattern 3: Context Resets with Structured Handoff

### What

Each OODA iteration spawns a **fresh Planner call** with a minimal handoff document instead of accumulating context from prior iterations.

### Why

The article says: "context resets — clearing the context window entirely and starting a fresh agent, combined with a structured handoff" outperforms compaction. Our current iteration loop appends tried_factors, tried_models, verdicts, and suggestions into `_iteration_context`, growing the prompt each iteration. By iteration 3, the LLM is anchored to prior failures.

### How

**Handoff document** (replaces `_iteration_context`):
```
Contract: Sharpe > 0.8, overfit < 2.0, min 500 samples
Avoid these factors: [momentum_20, vol_reversal, shock_reversal]
Avoid these model types: [gradient_boosting (Sharpe 0.3)]
Best result so far: Sharpe 0.3
Playbook size: 12 entries
Exploration mode: balanced
Iteration: 2 of 3
```

**What's excluded** (the anchoring context):
- No failure reasoning ("the momentum factor had negative IC because...")
- No evaluator suggestions ("try combining with volume...")
- No stack traces or error details
- No full result dicts from prior iterations

**Implementation:**
- `_run_cycle_inner` builds a handoff dict at the end of each iteration
- The handoff is passed to the next iteration's `orient()` and `decide()` calls
- The Planner receives only the handoff, not the accumulated iteration history
- `_iteration_context` becomes a list of handoff dicts (for logging) but is NOT injected into the Planner prompt

### Key Decision

The handoff tells the fresh Planner **what to avoid** and **what bar to clear**, but not **why** prior attempts failed. The "why" is what anchors the model to failed approaches. The "what" is what prevents repetition.


## Pattern 4: Auto-Tuning Evaluator

### What

A self-correcting feedback loop where the evaluator tracks its own judgment divergences and calibrates over time.

### Why

The article says "out of the box, Claude is a poor QA agent" and the fix is iterative tuning. Our statistical validation prompt is a static set of rules. A dynamic calibration loop adapts to the specific failure modes this system encounters.

### How

**Divergence tracking:**
- When the OODA evaluator says "pursue" based on in-sample metrics, the Evaluator agent runs held-out backtest
- If held-out Sharpe < 50% of in-sample Sharpe, or held-out Sharpe < 0: log a **divergence**
- Divergence entry in Playbook:
  ```json
  {
    "entry_type": "evaluator_divergence",
    "content": {
      "in_sample_sharpe": 2.1,
      "held_out_sharpe": -0.3,
      "test_accuracy": 0.53,
      "overfit_ratio": 1.8,
      "factors_used": ["momentum_20", "vol_reversal"],
      "model_type": "gradient_boosting",
      "what_was_misleading": "high in-sample Sharpe with barely-above-random accuracy"
    }
  }
  ```

**Calibration cycle** (every N cycles, e.g. every 5):
1. Query Playbook for recent `evaluator_divergence` entries
2. LLM analyzes patterns: "3 of 5 divergences had test_accuracy < 0.54 — accuracy is a better predictor than Sharpe"
3. LLM proposes a calibration rule: "Reject strategies with test_accuracy < 0.54 regardless of Sharpe"
4. Rule is appended to the evaluator system prompt and saved to Playbook as `evaluator_calibration`
5. Next cycle's evaluator uses the updated prompt

**New Playbook entry types:**
- `evaluator_divergence` — logged when evaluator was wrong
- `evaluator_calibration` — logged when a new calibration rule is added

**Safety:**
- Calibration rules can only tighten, never relax (can't lower the bar)
- Maximum 10 calibration rules in the prompt (oldest pruned)
- Config hard floors from sprint contracts always take precedence

### Key Decision

Fully automatic — no human review of calibration updates. The Playbook provides the audit trail. If a calibration rule is too aggressive (rejects everything), the system will stop pursuing and the next calibration cycle will detect "0 strategies pursued in 5 cycles" and adjust.


## Pattern 5: Scaffolding A/B Testing

### What

A structured system to test which scaffolding components are still necessary, measuring outcomes with and without each component.

### Why

The article says "every component in a harness encodes an assumption about what the model can't do on its own, and those assumptions are worth stress testing." As models improve, some scaffolding becomes dead weight.

### How

**Never-skip tier** (security and correctness, always on):
- AST validation + sandbox enforcement (`security.py`)
- Statistical validation in evaluator prompt
- Compliance veto on live trades
- Sprint contract hard floors
- Held-out evaluator backtest

**Testable tier** (can safely skip and measure):

| Component | What to measure | Skip method |
|-----------|----------------|-------------|
| Workflow templates | Plan quality (Sharpe, trade count) | Force LLM Planner, skip template match |
| Narration | User comprehension (manual) | Skip CHAT_NARRATIVE on step start |
| Agent manifest in prompts | Output quality, correct data flow | Strip manifest from one agent's system prompt |
| Factor AST pre-validation | Error rate in sandbox | Let sandbox catch errors naturally |
| Planner task schema reference | Task dict correctness | Remove schema section from Planner prompt |

**Tracking:**
- Each testable component has a `scaffolding_experiment` Playbook entry type
- Entry logs: component name, enabled/disabled, cycle outcomes (Sharpe, errors, LLM calls)
- After 10+ cycles per component, compare outcomes

**Implementation:**
- Config key `scaffolding_experiments` with list of components to test
- On each cycle, randomly disable one testable component (max one at a time)
- Log the experiment to Playbook
- Periodic review (manual or LLM-assisted) to decide what to remove

**New Playbook entry type:**
- `scaffolding_experiment` — logs component, enabled/disabled, outcome metrics

### Key Decision

Only one component disabled per cycle to isolate effects. Never-skip tier is hardcoded, not configurable. Experiments are opt-in via config — disabled by default.


## New Playbook Entry Types Summary

| Type | Purpose |
|------|---------|
| `evaluator_divergence` | Evaluator was wrong — logged for calibration |
| `evaluator_calibration` | New calibration rule added to evaluator prompt |
| `scaffolding_experiment` | A/B test result for a scaffolding component |

## New Config Keys

```yaml
contracts:
  min_sharpe: 0.0
  max_overfit_ratio: 3.0
  min_sample_size: 200
  min_trades: 10
  min_held_out_sharpe: 0.0
  held_out_months: 3

evaluator:
  calibration_interval: 5        # Cycles between calibration runs
  max_calibration_rules: 10
  divergence_threshold: 0.5      # held_out / in_sample ratio below this = divergence

scaffolding_experiments:
  enabled: false
  components: []                  # e.g. ["workflow_templates", "factor_validation"]
```

## Implementation Order

1. **Sprint contracts** — foundation for everything else (contract on Plan, config floors, Planner emits thresholds)
2. **Evaluator agent** — independent held-out validation (new agent, DAG position, data splitting)
3. **Context resets** — handoff document replaces iteration context accumulation
4. **Auto-tuning** — divergence tracking + calibration cycle (requires evaluator agent first)
5. **A/B testing** — scaffolding experiments (lowest priority, long-running)
