# Diagnostic Feedback Loop - Complete Summary

## Problem Identified

The QuantClaw orchestration engine is a **state machine, not an intelligent system**:

```
Current Behavior (Broken):
  Train → Validate → Allocate → Deploy (0 orders) 
    ↓
  "Verdict: iterate (no history). 0 LLM calls used."
  ↓
  [Repeat 500+ times with identical failure]
```

**Root Cause:** The system has no feedback mechanism to diagnose WHY actions fail or ADAPT strategy.

---

## Solution Delivered

Built a **three-layer diagnostic architecture**:

### Layer 1: Anomaly Detection (`diagnostics.py`)
Identifies 9 distinct problem categories:
- **Validation anomalies**: Held-out beats in-sample, metric degradation, weak signals, overfitting
- **Execution anomalies**: Zero orders despite allocations, all deployments fail
- **Portfolio anomalies**: Stalled promotions, portfolio stagnation, Sharpe plateau

```python
anomalies = AnomalyDetector.detect_validation_anomalies(evaluation)
anomalies.extend(AnomalyDetector.detect_execution_anomalies(summary))
anomalies.extend(AnomalyDetector.detect_portfolio_anomalies(campaign))
```

### Layer 2: Diagnostic Routing (`diagnostic_router.py`)
Routes each anomaly to the appropriate **expert agent**:

| Anomaly | Agent | Task |
|---------|-------|------|
| `held_out_outperforms_insample` | Debugger | `audit_validation_data_pipeline` |
| `zero_orders_with_allocations` | Debugger | `audit_paper_deployment_executor` |
| `metric_degradation` | Researcher | `investigate_model_drift` |
| `stalled_watchlist_promotion` | Researcher | `analyze_candidate_promotion_barriers` |
| `sharpe_plateau` | Researcher | `discover_new_trading_signals` |
| ... | ... | ... |

### Layer 3: OODA Integration (in `ooda.py`)
Inserts diagnostic feedback loop into evaluation phase:

```python
# OLD: evaluation = evaluate_results()
# NEW:
evaluation = evaluate_results()              # Generate initial verdict
anomalies = detect_anomalies(evaluation)    # Find problems
if anomalies:
    findings = await invoke_diagnostics()   # Get expert analysis
    evaluation.update(findings)              # Integrate insights
    verdict = reconsider_verdict(findings)   # Possibly change decision
```

---

## What's Built (Ready to Use)

### ✅ Complete
1. **AnomalyDetector** class
   - 9 detection methods (validation, execution, portfolio)
   - Severity ranking (critical, high, medium, low)
   - Context-rich findings (ratios, trends, thresholds)

2. **DiagnosticRouter** class
   - 9 routing handlers (one per anomaly type)
   - Builds diagnostic plans
   - Executes via existing dispatcher

3. **Integration Plan** (detailed step-by-step)
   - Modification points in ooda.py
   - New event types
   - Diagnostic task definitions

### ⏳ Remaining (Implementation)

1. **Modify ooda.py** (120 lines)
   - Initialize DiagnosticRouter in `__init__`
   - Add anomaly detection loop in `_evaluate_results()`
   - Invoke diagnostic router for top anomalies
   - Adjust verdict based on findings

2. **Add diagnostic tasks** to Debugger & Researcher (~200 lines)
   - Debugger: audit_validation_pipeline, audit_executor, diagnose_overfitting
   - Researcher: investigate_drift, analyze_signals, find_opportunities

3. **Add event types** (5 lines)
   - `DIAGNOSTIC_ANOMALY_DETECTED`
   - `DIAGNOSTIC_INVESTIGATION_COMPLETE`

4. **Test & validate** (verify diagnostics are invoked correctly)

---

## Expected Behavior After Integration

### Before (Current):
```
Iteration 387: Paper deployment produced 0 orders
Verdict: iterate (no history). 0 LLM calls used.
```

### After (With Diagnostics):
```
Iteration 387: Paper deployment produced 0 orders

ANOMALY DETECTED: zero_orders_with_allocations (CRITICAL)
  Invoked: debugger.audit_paper_deployment_executor
  Finding: Executor missing cash balance check — portfolio all-in on one strategy
  
ANOMALY DETECTED: stalled_watchlist_promotion (HIGH)
  Invoked: researcher.analyze_candidate_promotion_barriers
  Finding: Top candidate beats incumbent by 30% Sharpe, ready to promote
  
ACTIONS TAKEN:
  - Retire underperforming strategy
  - Promote top candidate (gradient_boosting_54d21e7a)
  - Rebalance portfolio to inject cash
  - Verify executor logic fix
  
RESULT: Next iteration executes 15 rebalance orders across portfolio
LLM calls: 2 (diagnostic reasoning agents)
```

---

## Key Architectural Changes

### Enable Active Learning
- ❌ OLD: Execute steps → iterate if needed
- ✅ NEW: Execute steps → diagnose problems → adapt strategy → iterate

### Integrate Expert Agents
- ❌ OLD: Only Train, Validate, Allocate agents in loop
- ✅ NEW: Also invoke Debugger, Researcher for diagnosis

### Make Decisions Intelligently
- ❌ OLD: "Orders = 0, so iterate" (mechanical)
- ✅ NEW: "Orders = 0 because executor is broken. Need to fix X." (reasoned)

### Track Learning
- ❌ OLD: Zero playbook entries from diagnostic reasoning
- ✅ NEW: Record findings, update gates, improve next cycle

---

## Success Metrics

After implementation, measure:

✅ **LLM calls per cycle** (was 0, should be 2-3 for diagnostics)
✅ **Anomalies detected per cycle** (when problems occur)
✅ **Diagnosis accuracy** (can Debugger actually find bugs?)
✅ **Verdict changes** (do findings cause verdict adjustments?)
✅ **Campaign improvement** (does active learning lead to better Sharpe?)
✅ **Stall cycles reduced** (fewer iterations in "iterate" state)

---

## Files Created

1. **`quantclaw/orchestration/diagnostics.py`** (220 lines)
   - AnomalyDetector class with 9 detection methods

2. **`quantclaw/orchestration/diagnostic_router.py`** (200 lines)
   - DiagnosticRouter class with 9 routing handlers

3. **`FEEDBACK_LOOP_PLAN.md`** (detailed architecture and phases)

4. **`INTEGRATION_STEPS.md`** (line-by-line integration guide)

---

## Next Steps

1. **Review** the created classes to validate approach
2. **Modify ooda.py** following INTEGRATION_STEPS.md
3. **Implement** diagnostic tasks in debugger.py and researcher.py
4. **Add** event types to events/types.py
5. **Test** with mock anomalies (e.g., simulate zero orders, metric inversion)
6. **Monitor** next campaign cycle for diagnostic invocations
7. **Iterate** on diagnostic accuracy and suggestion quality

---

## Impact

This transforms QuantClaw from a **mechanical choreographer** into an **intelligent orchestrator**.

Instead of blindly iterating when things fail, the system now:
- 🔍 **Diagnoses** what's wrong
- 🧠 **Reasons** about causes
- 🎯 **Acts** on findings
- 📚 **Learns** for next cycle

The result: campaigns that **improve continuously** rather than loop endlessly.
