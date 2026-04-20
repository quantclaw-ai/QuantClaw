# Agents

QuantClaw's workforce. Every agent extends `BaseAgent`, implements `execute(task) -> AgentResult`, and runs inside the OODA loop's ACT phase via the Dispatcher.

## Agent Lifecycle

```
Dispatcher.execute_plan(plan)
  -> agent.run(task)
       -> execute(task)          # up to 3 retries
       -> verify(result)         # success check
       -> on_failure(error)      # retry hook
  -> EventBus: AGENT_TASK_COMPLETED | AGENT_TASK_FAILED
```

Every agent gets `_upstream_results` injected when it depends on a prior step.

---

## Catalog

### Miner
- **Purpose:** Discover alpha factors via evolutionary LLM generation
- **Type:** LLM (gpt-4o, temp 0.9)
- **Input:** `goal`, `symbols`, `generations`, `playbook_context`
- **Output:** `factors[]` with `name`, `code`, `ic`, `sharpe`; `best_sharpe`, `best_ic`
- **How:** Generates factor hypotheses via LLM, evaluates each in sandbox (IC, Rank IC, Sharpe), mutates top performers across generations

### Trainer
- **Purpose:** ML model training pipeline
- **Type:** Code-only (no LLM calls)
- **Input:** `model_type`, `model_params`, `symbols`, `forward_period`, `factors[]` or upstream Miner output
- **Output:** `model_path`, `features_used`, `strategy_code`, `strategy_path`
- **How:** Validates factor syntax (AST), generates training script, executes in sandbox, produces executable `Strategy` class
- **Models:** sklearn (gradient_boosting, random_forest, ridge, linear, lasso, elasticnet), xgboost, lightgbm, lstm, transformer, tcn, gru, timefm, chronos, prophet, custom

### Backtester
- **Purpose:** Strategy performance evaluation
- **Type:** Code-only
- **Input:** `strategy_code`, `symbols`, `start`, `end`
- **Output:** Returns, drawdown, Sharpe ratio, trade statistics
- **How:** Executes strategy in sandbox against historical data

### Researcher
- **Purpose:** Web research and synthesis
- **Type:** LLM (opus, temp 0.7)
- **Input:** `topic`, `task`, `context`
- **Output:** `findings[]`, `suggested_factors[]`, `suggested_models[]`, `suggested_data_sources[]`
- **How:** Web search + LLM synthesis into structured recommendations

### Ingestor
- **Purpose:** Market data fetching
- **Type:** Code-only
- **Input:** `symbols`, `query`, `start`, `end`
- **Output:** `ohlcv{}` (DataFrames), `search[]` (web intelligence)
- **How:** Data plugins (yfinance default) + web search provider

### Reporter
- **Purpose:** Result summarization
- **Type:** Hybrid (template tables + LLM executive summary)
- **Input:** `_upstream_results` from prior pipeline steps
- **Output:** `report` (formatted), `summary` (LLM paragraph), `data`
- **How:** Programmatic table generation + one-paragraph LLM synthesis

### Executor
- **Purpose:** Order submission
- **Type:** Code-only
- **Input:** `orders[]`, `strategy_path`
- **Output:** `orders_executed`, `orders[]` (filled/submitted)
- **How:** Paper trading (default) or live broker plugin; gated by trust level >= TRUSTED

### Risk Monitor
- **Purpose:** Portfolio risk surveillance
- **Type:** Code-only, daemon
- **Input:** `portfolio`, `positions[]`, `equity`, `current_drawdown`
- **Output:** `risk_level`, `issues[]`, `sector_weights`, `total_exposure`
- **Checks:** Max drawdown, position concentration, sector diversification, leverage, auto-liquidation threshold

### Compliance
- **Purpose:** Trade rule enforcement
- **Type:** Code-only
- **Input:** `trades[]`, `portfolio_value`, `current_drawdown`
- **Output:** `compliant` (bool), `violations[]`
- **Rules:** Position size limits, drawdown limits, restricted symbol list

### Cost Tracker
- **Purpose:** LLM API cost monitoring
- **Type:** Code-only
- **Input:** task type (`report`, `check_budget`, `estimate`), `steps[]`
- **Output:** `estimated_cost_usd`, `budget`, `remaining_usd`, `breakdown[]`
- **How:** Estimates costs by model assignment per agent, tracks against budget

### Sentinel
- **Purpose:** Safety watchdog
- **Type:** Code-only, daemon, event-driven
- **Input:** EventBus event stream (no task input)
- **Output:** `active_rules`, `alerts_fired[]`, `failure_counts`
- **Triggers:** Agent failures, drawdown breaches, cost warnings, market gaps

### Debugger
- **Purpose:** Pipeline error diagnosis
- **Type:** LLM (opus, temp 0.3)
- **Input:** `error`, `context`
- **Output:** Diagnosis and suggested fix

### Scheduler
- **Purpose:** Cron event loop coordination
- **Type:** Code-only, daemon
- **How:** Fires scheduled tasks; actual loop runs in `daemon.py`

---

## Model Assignments

| Agent | Model | Provider | Temperature |
|-------|-------|----------|-------------|
| miner | gpt-4o | openai | 0.9 |
| researcher | opus | anthropic | 0.7 |
| trainer | opus | anthropic | 0.5 |
| scheduler | - | - | 0.5 |
| debugger | opus | anthropic | 0.3 |
| reporter | sonnet | anthropic | 0.3 |
| ingestor | opus | anthropic | 0.2 |
| backtester | opus | anthropic | 0.2 |
| sentinel | sonnet | anthropic | 0.2 |
| risk_monitor | opus | anthropic | 0.1 |
| executor | opus | anthropic | 0.1 |
| compliance | opus | anthropic | 0.1 |
| cost_tracker | sonnet | anthropic | 0.1 |

## Data Flow

Agents connect through DAG dependencies. Common pipelines:

```
Signal Hunting:    Researcher + Ingestor -> Miner -> Trainer -> Backtester -> Reporter
Go Live:           Compliance -> Risk Monitor -> Executor
Risk Response:     Risk Monitor -> Sentinel -> Reporter
```

Upstream results flow automatically via `_upstream_results` dict injection.
