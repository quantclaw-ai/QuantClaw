# Integration Steps for Diagnostic Feedback Loop

## Step 1: Initialize DiagnosticRouter in OODA.__init__

Add after line 79 in ooda.py:
```python
from quantclaw.orchestration.diagnostic_router import DiagnosticRouter
from quantclaw.orchestration.diagnostics import AnomalyDetector

# ... in __init__ ...
self._diagnostic_router = DiagnosticRouter(dispatcher)
self._anomaly_detector = AnomalyDetector()
self._prior_evaluation_sharpe: dict[str, float] = {}  # Track Sharpe history
```

## Step 2: Modify _evaluate_results to Include Diagnostic Loop

The new flow in _evaluate_results should be:

```
1. Generate initial evaluation (verdict + reasoning)
2. NEW: Detect anomalies
3. NEW: For each anomaly, invoke diagnostic agent
4. NEW: Integrate findings into evaluation
5. NEW: Adjust verdict if needed based on findings
6. Publish evaluation event
7. Return evaluation
```

## Step 3: Key Changes in _evaluate_results

After line 414 (end of paper cycle evaluation) and after line 476 (end of zero-trade detection), add:

```python
# NEW: Anomaly detection and diagnostic feedback
anomalies = []

# Detect validation anomalies
anomalies.extend(self._anomaly_detector.detect_validation_anomalies(
    evaluation=evaluation,
    prior_sharpe=self._prior_evaluation_sharpe.get("test_sharpe"),
))

# Detect execution anomalies
anomalies.extend(self._anomaly_detector.detect_execution_anomalies(summary))

# Detect portfolio/campaign anomalies
if self._campaign:
    campaign_dict = self._campaign.to_dict()
    anomalies.extend(self._anomaly_detector.detect_portfolio_anomalies(campaign_dict))

# Get top anomalies by severity
top_anomalies = self._anomaly_detector.get_top_anomalies(anomalies, max_count=3)

# Invoke diagnostic agents
diagnostic_findings = {}
if top_anomalies:
    logger.info(f"Detected {len(top_anomalies)} anomalies, invoking diagnostics...")
    
    for anomaly in top_anomalies:
        logger.info(f"  - {anomaly.name} ({anomaly.severity}): {anomaly.description}")
        
        # Build evaluation context for diagnostic agent
        eval_context = {
            "test_sharpe": best_result.get("sharpe", 0),
            "held_out_sharpe": best_result.get("held_out_sharpe", 0),
            "overfit_ratio": best_result.get("overfit_ratio", 1.0),
            "iteration": iteration,
            "summary": summary,
            "campaign": self._campaign.to_dict() if self._campaign else None,
            "portfolio_state": await self._deployment_allocator.get_state() if self._campaign else None,
        }
        
        # Invoke diagnostic router
        diag_result = await self._diagnostic_router.route_anomaly(anomaly, eval_context)
        
        if diag_result.status == AgentStatus.SUCCESS:
            diagnostic_findings[anomaly.name] = diag_result.data
            logger.info(f"    Finding: {diag_result.data.get('summary', 'completed')}")
        else:
            logger.warning(f"    Diagnostic failed: {diag_result.data}")

# Update evaluation with diagnostic findings
if "diagnostics" not in evaluation:
    evaluation["diagnostics"] = {}
evaluation["diagnostics"]["anomalies"] = [a.name for a in top_anomalies]
evaluation["diagnostics"]["findings"] = diagnostic_findings

# Adjust verdict based on findings
# If critical anomaly detected and no clear fix in findings, may need to abandon
for anomaly in top_anomalies:
    if anomaly.severity == "critical":
        findings = diagnostic_findings.get(anomaly.name, {})
        root_cause = findings.get("root_cause")
        
        if root_cause and "executor" in root_cause.lower():
            # Executor is broken — can't proceed with paper trading
            evaluation["verdict"] = "abandon"
            evaluation["reasoning"] = (
                f"Executor problem detected: {root_cause}. "
                "Cannot continue paper trading until fixed."
            )
            break
        elif root_cause and "data_leakage" in root_cause.lower():
            # Data leakage — model is invalid
            evaluation["verdict"] = "abandon"
            evaluation["reasoning"] = f"Data leakage detected: {root_cause}. Strategy is invalid."
            break

# Track Sharpe for next iteration
self._prior_evaluation_sharpe["test_sharpe"] = best_result.get("sharpe", 0)
self._prior_evaluation_sharpe["held_out_sharpe"] = best_result.get("held_out_sharpe", 0)
```

## Step 4: Update EventType to include diagnostics

Add to events/types.py if not already present:
- DIAGNOSTIC_ANOMALY_DETECTED
- DIAGNOSTIC_INVESTIGATION_COMPLETE

## Step 5: Publish diagnostic events

After diagnostic findings are collected:

```python
for anomaly in top_anomalies:
    findings = diagnostic_findings.get(anomaly.name, {})
    await self._bus.publish(Event(
        type=EventType.DIAGNOSTIC_INVESTIGATION_COMPLETE,
        payload={
            "anomaly": anomaly.name,
            "severity": anomaly.severity,
            "description": anomaly.description,
            "findings": findings,
        },
        source_agent="scheduler",
    ))
```

## Step 6: Add diagnostic task handlers to Debugger and Researcher

Both agents need to handle diagnostic tasks:

### Debugger tasks:
- `audit_validation_data_pipeline`: Check for data leakage, misalignment
- `audit_paper_deployment_executor`: Check executor logic, cash balance
- `audit_deployment_model_loading`: Check model files, feature loading
- `diagnose_overfitting`: Suggest parameter reductions or data augmentation

### Researcher tasks:
- `investigate_model_drift`: Analyze what changed, suggest adjustments
- `analyze_signal_weakness`: Discover missing factors or features
- `analyze_candidate_promotion_barriers`: Review compliance and performance gaps
- `discover_new_trading_signals`: Find new factors to improve Sharpe
- `find_new_allocation_opportunities`: Suggest portfolio rebalancing

## Summary of Changes

| File | Change | Lines | Impact |
|------|--------|-------|--------|
| ooda.py | Add diagnostic import | ~5 | Import new classes |
| ooda.py | Initialize router in __init__ | ~10 | Create router instance |
| ooda.py | Add anomaly detection loop | ~80 | Core feedback loop |
| ooda.py | Invoke diagnostic agents | ~50 | Execute diagnostics |
| ooda.py | Adjust verdict based on findings | ~20 | Make decisions |
| events/types.py | Add event types | ~5 | New event types |
| agents/debugger.py | Add diagnostic tasks | ~100 | Implement debugging |
| agents/researcher.py | Add diagnostic tasks | ~100 | Implement investigation |

Total: ~350 lines of new/modified code to enable active learning
