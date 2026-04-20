# QuantClaw Diagnostic Feedback Loop - Implementation Plan

## Current Problem

The OODA loop is **mechanically choreographed**, not intelligently orchestrated:
- Trains models → Validates them → Allocates capital → Deploys → Gets "0 orders executed"
- Response: "Verdict: iterate (no history). 0 LLM calls used."
- No diagnosis. No reasoning. Just repeat.

**Evidence from logs:**
```
Iteration 1: Paper deployment cycle ran but produced no rebalance orders.
Completed 1 iteration. Verdict: iterate (no history). 0 LLM calls used.

[500 iterations later...]

Iteration 387: Same result. Verdict: iterate. 0 LLM calls used.
```

---

## Solution: Active Diagnostic Feedback Loop

Transform the scheduler from a **state machine** (execute predetermined steps) into an **orchestrator** (reason about results, diagnose problems, adapt strategy).

### New Architecture

```
CURRENT (broken):
  train() → validate() → allocate() → deploy() → iterate()
  
NEW (intelligent):
  train() → validate() → ANOMALY_CHECK()
    ├─ YES: invoke DIAGNOSTIC_AGENT() → get findings → ADAPT_STRATEGY()
    └─ NO: allocate() → deploy() → monitor() → compare_vs_backtest() → feedback
```

---

## Components to Build

### 1. **AnomalyDetector** (new file)
Detects problems that should trigger investigation:

```python
class AnomalyDetector:
    """Identifies anomalies that warrant diagnostic agent investigation."""
    
    def detect_validation_anomalies(evaluation: dict) -> list[str]:
        """Detect suspicious validation metrics."""
        anomalies = []
        
        # Held-out beats in-sample (backwards from normal overfitting)
        if held_out_sharpe > test_sharpe:
            anomalies.append("held_out_outperforms_insample")
        
        # Metric degradation across iterations
        if new_sharpe < prior_sharpe * 0.8:
            anomalies.append("metric_degradation")
        
        # Held-out Sharpe too low
        if held_out_sharpe < 0.5:
            anomalies.append("weak_signal")
        
        # Overfit ratio too high
        if overfit_ratio > 1.2:
            anomalies.append("excessive_overfitting")
        
        return anomalies
    
    def detect_execution_anomalies(paper_state: dict) -> list[str]:
        """Detect execution/deployment problems."""
        anomalies = []
        
        # Zero orders despite valid allocations
        if orders_executed == 0 and active_deployments > 0:
            anomalies.append("zero_orders_with_allocations")
        
        # Watchlist stagnation (candidates never promoted)
        if watchlist_age > 50_cycles and no_promotions:
            anomalies.append("watchlist_candidates_never_promote")
        
        # Portfolio composition unchanged
        if positions_unchanged_for(20_cycles):
            anomalies.append("portfolio_stagnation")
        
        return anomalies
    
    def detect_campaign_anomalies(campaign: ProfitCampaign) -> list[str]:
        """Detect problems in profit campaign state."""
        anomalies = []
        
        # Best Sharpe stalling
        if best_sharpe_unchanged_for(100_cycles):
            anomalies.append("sharpe_plateau")
        
        # Large gap between best validated and active
        if gap_ratio > 1.5:
            anomalies.append("gap_between_candidate_and_active")
        
        return anomalies
```

### 2. **DiagnosticRouter** (new file)
Routes detected anomalies to appropriate diagnostic agents:

```python
class DiagnosticRouter:
    """Invokes diagnostic agents based on detected anomalies."""
    
    async def route_anomaly(self, anomaly: str, context: dict) -> AgentResult:
        """Dispatch anomaly to appropriate diagnostic agent."""
        
        routes = {
            "held_out_outperforms_insample": self._validate_data_pipeline,
            "zero_orders_with_allocations": self._debug_executor,
            "watchlist_candidates_never_promote": self._analyze_promotion_gates,
            "metric_degradation": self._investigate_model_drift,
            "sharpe_plateau": self._research_new_signals,
            # ...
        }
        
        agent_handler = routes.get(anomaly)
        if agent_handler:
            return await agent_handler(context)
        
        return AgentResult(status=AgentStatus.SKIPPED)
    
    async def _validate_data_pipeline(self, context: dict) -> AgentResult:
        """Call Debugger agent to audit data alignment."""
        # Invoke debugger agent with validation audit task
        plan = Plan(steps=[
            PlanStep(
                agent="debugger",
                task="audit_validation_data_pipeline",
                context=context,
            )
        ])
        return await self._dispatcher.execute(plan)
    
    async def _debug_executor(self, context: dict) -> AgentResult:
        """Call Debugger to audit deployment executor."""
        plan = Plan(steps=[
            PlanStep(
                agent="debugger",
                task="audit_paper_deployment_executor",
                context=context,
            )
        ])
        return await self._dispatcher.execute(plan)
    
    async def _analyze_promotion_gates(self, context: dict) -> AgentResult:
        """Call Researcher to investigate why candidates don't promote."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="analyze_candidate_promotion_barriers",
                context=context,
            )
        ])
        return await self._dispatcher.execute(plan)
    
    async def _investigate_model_drift(self, context: dict) -> AgentResult:
        """Call Researcher to investigate model degradation."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="investigate_model_performance_drift",
                context=context,
            )
        ])
        return await self._dispatcher.execute(plan)
    
    async def _research_new_signals(self, context: dict) -> AgentResult:
        """Call Researcher to discover new features/factors."""
        plan = Plan(steps=[
            PlanStep(
                agent="researcher",
                task="discover_new_trading_signals",
                context=context,
            )
        ])
        return await self._dispatcher.execute(plan)
```

### 3. **Integrate into OODA._evaluate_results()**
Modify the evaluation method to invoke diagnostics:

```python
async def _evaluate_results(self, results: dict, iteration: int) -> dict:
    """Evaluate with diagnostic feedback loop."""
    
    summary = self._summarize_cycle_results(results)
    best_sharpe = summary["best_sharpe"]
    
    # ... existing evaluation logic ...
    
    # NEW: Detect anomalies
    anomalies = AnomalyDetector.detect_validation_anomalies(evaluation)
    anomalies += AnomalyDetector.detect_execution_anomalies(summary)
    anomalies += AnomalyDetector.detect_campaign_anomalies(self._campaign)
    
    # NEW: If anomalies detected, invoke diagnostic agents
    if anomalies:
        diagnostic_findings = {}
        for anomaly in anomalies[:3]:  # Limit to top 3 per cycle
            result = await self._diagnostic_router.route_anomaly(
                anomaly,
                context={
                    "evaluation": evaluation,
                    "summary": summary,
                    "campaign": self._campaign.to_dict(),
                    "iteration": iteration,
                }
            )
            diagnostic_findings[anomaly] = result.data
        
        # Integrate findings into evaluation
        evaluation["diagnostics"]["findings"] = diagnostic_findings
        evaluation["diagnostics"]["anomalies"] = anomalies
        
        # If findings suggest specific action, adjust verdict
        if diagnostic_findings.get("zero_orders_with_allocations", {}).get("root_cause"):
            cause = diagnostic_findings["zero_orders_with_allocations"]["root_cause"]
            if cause == "executor_broken":
                evaluation["verdict"] = "abandon"
                evaluation["reasoning"] = f"Executor is broken: {cause}"
    
    return evaluation
```

### 4. **Decision Gates**
Add explicit decision points that require reasoning:

```python
async def _should_promote_candidate(self, candidate: str, incumbent: str) -> bool:
    """Require LLM reasoning before promoting a candidate strategy."""
    
    # Don't auto-promote; ask Planner to reason about it
    plan = await self._planner.create_plan({
        "goal": f"Should we promote {candidate} to replace {incumbent}?",
        "context": {
            "candidate_stats": self._campaign.get_strategy_stats(candidate),
            "incumbent_stats": self._campaign.get_strategy_stats(incumbent),
            "portfolio_state": self._deployment_allocator.get_state(),
            "compliance_rules": self._guardrails.to_dict(),
        }
    })
    
    # Execute decision plan (may run backtest comparison, risk checks, etc.)
    results = await self._dispatcher.execute(plan)
    
    # Parse recommendation
    recommendation = results.get("decision_step").data.get("recommendation")
    return recommendation == "promote"
```

### 5. **Feedback Integration Points**

Add these checks at key moments:

```
OBSERVE
  → Check for stale data, market regime changes
  
ORIENT
  → Assess current portfolio drift
  
EVALUATE
  ✓ NEW: Detect anomalies
  ✓ NEW: Invoke diagnostics
  ✓ NEW: Apply findings to decision
  
DECIDE
  ✓ NEW: Require reasoning before promotion/demotion
  ✓ NEW: Ask "should we really iterate again?" before continuing
  
LEARN
  ✓ NEW: Record diagnostic findings in playbook
  ✓ NEW: Update promotee/demotee gates based on findings
```

---

## Expected Outcomes

### Before (Current):
```
[300+ iterations, 0 orders, same error message]
Verdict: iterate (no history). 0 LLM calls used.
```

### After (With Diagnostic Loop):
```
Iteration 385: Paper deployment cycle produced 0 orders.
ANOMALY DETECTED: zero_orders_with_allocations
Invoking: debugger.audit_paper_deployment_executor
  → Finding: Executor missing cash balance check in rebalance logic
  → Root cause: Portfolio all-in on one strategy, no cash for rebalancing

Invoking: researcher.analyze_candidate_promotion_barriers
  → Finding: Top candidate (gradient_boosting_54d21e7a) beats incumbent by 30% Sharpe
  → Recommendation: Promote candidate and retire underperformer

ACTION: Retire inactive strategy, promote candidate, inject cash
RESULT: Next cycle executes 15 orders across rebalanced portfolio
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (2-3 hours)
- Create `AnomalyDetector` class
- Create `DiagnosticRouter` class  
- Wire into `_evaluate_results()`
- Add diagnostic agent tasks to Debugger, Researcher

### Phase 2: Decision Gates (1-2 hours)
- Add `_should_promote_candidate()` decision gate
- Integrate reasoning into portfolio allocation
- Add checks before major strategy changes

### Phase 3: Feedback Integration (1 hour)
- Record diagnostic findings in playbook
- Update promotion/demotion thresholds based on findings
- Add anomaly history tracking

### Phase 4: Validation (2-3 hours)
- Run against stalled campaign logs
- Verify anomalies are detected correctly
- Verify diagnostic agents are invoked
- Test that verdicts change based on findings

---

## Files to Create/Modify

**New:**
- `quantclaw/orchestration/diagnostics.py` - AnomalyDetector
- `quantclaw/orchestration/diagnostic_router.py` - DiagnosticRouter
- `quantclaw/agents/debugger_tasks.py` - Debugger task definitions

**Modified:**
- `quantclaw/orchestration/ooda.py` - Integrate anomaly detection + routing
- `quantclaw/agents/debugger.py` - Add diagnostic tasks
- `quantclaw/agents/researcher.py` - Add diagnostic task handlers

---

## Success Criteria

✓ When 0 orders are executed for 3+ consecutive cycles, system diagnoses why
✓ When held-out outperforms in-sample, system investigates data leakage
✓ When watchlist candidate is never promoted, system analyzes barriers
✓ LLM agents are invoked to reason about problems (LLM calls > 0)
✓ Verdicts change based on diagnostic findings, not just mechanical rules
✓ System actively adapts strategy rather than mechanically iterating
