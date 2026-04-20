# Miner & Trainer Agents — Design Document

**Date:** 2026-04-06
**Status:** Approved (v3 — all 18 audit issues fixed)
**Author:** Harry + Claude
**Depends on:** Sandbox, Scheduler Intelligence, Playbook (all implemented)
**Related:** [Workflow Efficiency](2026-04-06-workflow-efficiency-design.md), [Scheduler Intelligence](2026-04-06-scheduler-intelligence-design.md)

## Problem

The Miner and Trainer agents are stubs. The Miner should discover alpha factors using an evolutionary loop. The Trainer should build ML models from those factors. Both execute LLM-generated code in the sandbox. The Researcher agent collaborates with all agents as an R&D advisor, mediated through the Scheduler.

## Miner Agent

Discovers alpha factors from any data type (price, fundamental, alternative/sentiment). Uses an evolutionary loop inspired by QuantaAlpha. **Requires LLM calls** for creative hypothesis generation — this is the core creative agent.

### Internal Loop (3-5 generations per task)

```
1. HYPOTHESIZE — LLM generates factor ideas (uses most capable model)
   Input: data description, goal, Playbook context (what worked/failed)
   Output: {hypothesis, proposed_code, data_types_needed}

2. IMPLEMENT — Write executable factor code
   Factor code: takes DataFrame, returns scores per symbol

3. EVALUATE — Run factor in sandbox via factor_evaluator.py
   Metrics: IC, Rank IC, turnover, Sharpe of long-short portfolio

4. FEEDBACK — Feed ALL metrics back to LLM (not just Sharpe)
   "IC was 0.02 (weak). Rank IC 0.05. Turnover 0.8 (high). Sharpe 0.3."

5. EVOLVE — LLM chooses strategy:
   - Mutation: tweak parameters ("try 10d instead of 5d")
   - Crossover: combine two factors ("momentum × volatility")
   - Exploration: try completely new idea

6. RECORD — Save best factor(s) to Playbook as FACTOR_LIBRARY entry
```

### Task Interface

The Miner receives Playbook context via the task dict. The Scheduler injects it when composing the DAG. Upstream results from Ingestor/Researcher arrive via `_upstream_results`.

```python
await miner.execute({
    "task": "discover_factors",
    "goal": "find momentum alpha",
    "data_types": ["price", "fundamental", "sentiment"],
    "symbols": ["AAPL", "MSFT", ...],
    "generations": 3,
    "playbook_context": [...],  # Scheduler injects from Playbook query
    "_upstream_results": {       # Dispatcher injects from dependent steps
        "0": {"findings": [...]},  # Researcher output
        "1": {"ohlcv": {...}},     # Ingestor output
    },
})
```

### Returns

Returns ALL evaluation metrics (IC, Rank IC, turnover, Sharpe) — not just Sharpe. The Scheduler's `_iteration_context` preserves the full metrics for informed follow-up decisions.

```python
AgentResult(status=SUCCESS, data={
    "factors": [
        {"name": "momentum_vol_adj",
         "hypothesis": "5-day momentum adjusted for volatility",
         "code": "df['close'].pct_change(5) / df['close'].pct_change(5).rolling(20).std()",
         "data_types": ["price"],
         "metrics": {"ic": 0.05, "rank_ic": 0.08, "sharpe": 1.2, "turnover": 0.3},
         "lineage": {"parent": None, "generation": 0, "method": "exploration"}},
    ],
    "generations_run": 3,
    "best_sharpe": 1.2,
    "best_ic": 0.05,
    "best_rank_ic": 0.08,
})
```

### Factor Representation

Factors are stored as code string + rich metadata in the Playbook's `FACTOR_LIBRARY` entry type:

```python
{"name": "momentum_vol_adj",
 "hypothesis": "5-day momentum adjusted for volatility captures short-term trends",
 "code": "df['close'].pct_change(5) / df['close'].pct_change(5).rolling(20).std()",
 "data_types": ["price"],
 "metrics": {"ic": 0.05, "rank_ic": 0.08, "sharpe": 1.2, "turnover": 0.3},
 "lineage": {"parent": "momentum_5d", "generation": 2, "method": "mutation"}}
```

### Sandbox Execution — Factor Evaluation

The Miner generates a **complete self-contained Python script** that wraps the factor code with data loading, evaluation, and JSON output. The sandbox runs arbitrary Python — it doesn't provide DataFrame loading. The Miner's LLM generates the full script.

Factor evaluation runs via `factor_evaluator.py` — a helper module that computes IC, Rank IC, turnover, and long-short Sharpe:

```python
# quantclaw/sandbox/factor_evaluator.py
# This runs INSIDE the sandbox subprocess
#
# Usage: import and call from Miner-generated scripts
# Computes: IC, Rank IC, turnover, long-short Sharpe
#
# Example Miner-generated script sent to sandbox:
#
# import pandas as pd
# import numpy as np
# import json
# from pathlib import Path
#
# # Load data (parquet files written by sandbox.execute_strategy)
# data = {}
# for f in Path("data").glob("*.parquet"):
#     data[f.stem] = pd.read_parquet(f)
#
# # Factor code (LLM-generated)
# def compute_factor(df):
#     return df['close'].pct_change(5) / df['close'].pct_change(5).rolling(20).std()
#
# # Compute factor scores for all symbols
# scores = {}
# for symbol, df in data.items():
#     scores[symbol] = compute_factor(df)
#
# # Evaluate using factor_evaluator
# from quantclaw.sandbox.factor_evaluator import evaluate_factor
# metrics = evaluate_factor(scores, data, forward_period=5)
# print(json.dumps(metrics))
```

### Evaluation Metrics (computed by factor_evaluator.py)

- **IC (Information Coefficient)**: Pearson correlation between factor scores and forward returns
- **Rank IC**: Spearman rank correlation (more robust than IC)
- **Turnover**: daily change in factor ranking (lower = better, less trading)
- **Long-short Sharpe**: Sharpe ratio of going long top quintile, short bottom quintile

These are computed using pandas/numpy only. No external libraries needed.

## Trainer Agent

Takes factors (from Miner/Playbook) and/or raw data (from Ingestor) and builds ML models wrapped as Strategy classes. Supports everything from simple linear models to foundation time series models and custom user-provided architectures.

**The Trainer's `execute()` method is code-only — no LLM call.** The Scheduler and Researcher decide model type and hyperparameters. The Trainer receives those decisions as task parameters and executes the mechanical pipeline: feature engineering → train → evaluate → save → generate Strategy class. All training runs in the sandbox.

### Flow

```
1. FEATURE ENGINEERING — Convert factor codes into feature matrix
   Run each factor's code against data → one column per factor per symbol

2. LABEL CREATION — Forward returns as labels
   predict_period=5 → 5-day forward returns

3. TRAIN/TEST SPLIT — Walk-forward split (no look-ahead bias)
   80% train, 20% test, time-ordered

4. MODEL TRAINING — Model from registry or custom path
   Classical: scikit-learn (RF, GBM, Ridge)
   Deep Learning: PyTorch (LSTM, TCN, Transformer)
   Foundation: TimeFM, Chronos
   Custom: user-provided model class

5. EVALUATION — Out-of-sample metrics
   Test Sharpe, accuracy, feature importance (where applicable), overfit ratio

6. SAVE MODEL — Persist to data/models/{model_id}.pt or .pkl
   Models are expensive to train — persist, don't regenerate

7. GENERATE STRATEGY — Wrap model reference in a Strategy class
   Strategy saved to data/strategies/{strategy_id}.py
   Strategy loads model at runtime via model_path
```

### Task Interface

The Trainer accepts the **full Miner output format** for factors. It uses `name` and `code` fields, ignores extra metadata (metrics, lineage, hypothesis). This means Miner output plugs directly into Trainer input without transformation.

```python
await trainer.execute({
    "task": "train_model",
    "factors": [
        # Full Miner format accepted — Trainer uses name + code, ignores rest
        {"name": "momentum_5d", "code": "df['close'].pct_change(5)",
         "hypothesis": "...", "metrics": {...}, "lineage": {...}},
        {"name": "vol_20d", "code": "df['close'].rolling(20).std()"},
    ],
    "symbols": ["AAPL", "MSFT", ...],
    "model_type": "gradient_boosting",  # Scheduler/Researcher decides this
    "model_params": {},  # Scheduler/Researcher decides hyperparams
    "model_path": "",  # for custom: path to user model class
    "model_class": "",  # for custom: class name to import
    "forward_period": 5,
    "start": "2020-01-01",
    "end": "2024-12-31",
    "_upstream_results": {  # Dispatcher injects from dependent steps
        "2": {"factors": [...]},  # Miner output (step 2 in DAG)
    },
})
```

When Trainer receives `_upstream_results` from a Miner step, it automatically extracts factors from there if `factors` is not explicitly provided in the task.

### Returns

```python
AgentResult(status=SUCCESS, data={
    "model_type": "transformer",
    "model_id": "transformer_abc123",
    "model_path": "data/models/transformer_abc123.pt",
    "strategy_path": "data/strategies/transformer_abc123.py",
    "features_used": ["momentum_5d", "vol_20d"],
    "feature_importance": {"momentum_5d": 0.65, "vol_20d": 0.35},
    "metrics": {
        "train_sharpe": 1.8,
        "test_sharpe": 1.1,
        "accuracy": 0.54,
        "overfit_ratio": 1.64,
    },
    "strategy_code": "class Strategy:\n  ...",
    "sharpe": 1.1,
})
```

### Model Registry

| Category | Models | Library | Model persistence |
|---|---|---|---|
| **Classical** | Ridge, Lasso, ElasticNet | scikit-learn | `.pkl` (joblib) |
| **Ensemble** | RandomForest, GradientBoosting, XGBoost, LightGBM | scikit-learn, xgboost, lightgbm | `.pkl` (joblib) |
| **Time Series** | ARIMA, Prophet | statsmodels, prophet | `.pkl` |
| **Deep Learning** | LSTM, GRU, TCN, Transformer | PyTorch | `.pt` (state_dict) |
| **Foundation** | TimeFM, TimeGPT, Chronos | huggingface/specialized | `.pt` or API-based |
| **Custom** | User-provided model class | loaded from file path | format defined by user |

For simple models (Ridge, RF), coefficients can be embedded inline in the Strategy class. For complex models (LSTM, Transformer), the model is saved to `data/models/` and the Strategy class loads it by path.

### Dependency Validation

Before attempting training, the Trainer checks that required packages are importable:

```python
MODEL_REQUIREMENTS = {
    "gradient_boosting": [],
    "random_forest": [],
    "xgboost": ["xgboost"],
    "lightgbm": ["lightgbm"],
    "lstm": ["torch"],
    "transformer": ["torch"],
    "tcn": ["torch"],
    "timefm": ["torch", "transformers"],
    "chronos": ["torch", "chronos-forecasting"],
    "prophet": ["prophet"],
}

def _check_dependencies(self, model_type: str) -> list[str]:
    """Returns list of missing packages. Empty = all available."""
    missing = []
    for pkg in MODEL_REQUIREMENTS.get(model_type, []):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing
```

If dependencies are missing, the Trainer returns a clear error with install instructions. The Scheduler can then decide to try a different model type or ask the CEO to install the dependency.

### Foundation Model API Integration

Foundation models (TimeFM, Chronos, TimeGPT) have additional requirements:

- **TimeFM / Chronos**: Downloaded from HuggingFace. Requires `HF_TOKEN` environment variable for gated models. First use downloads the model to `~/.cache/huggingface/`. Subsequent uses load from cache.
- **TimeGPT**: API-based. Requires `TIMEGPT_API_KEY` in config. No local model download.

The Trainer checks for these in `_check_dependencies()` and reports clearly:
```
"Model 'timefm' requires: pip install torch transformers. 
 For gated models, set HF_TOKEN environment variable."
```

### Custom Model Validation

Before training, the Trainer validates that custom model classes have the required interface:

```python
def _validate_custom_model(self, model_path: str, model_class: str) -> str | None:
    """Returns error message if invalid, None if valid."""
    path = Path(model_path)
    if not path.exists():
        return f"Custom model file not found: {model_path}"
    
    spec = importlib.util.spec_from_file_location("custom_model", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    cls = getattr(module, model_class, None)
    if cls is None:
        return f"Class '{model_class}' not found in {model_path}"
    
    required_methods = ["fit", "predict", "save", "load"]
    missing = [m for m in required_methods if not hasattr(cls, m)]
    if missing:
        return f"Custom model missing methods: {missing}"
    
    return None
```

### Sandbox Execution — Model Persistence

**IMPORTANT:** The sandbox normally deletes its temp directory after execution. But trained models must persist. The Trainer's sandbox execution script explicitly saves models to `data/models/` (which is outside the temp directory) before the sandbox cleans up:

```python
# Inside the sandbox-executed training script:
import joblib
from pathlib import Path

# Train model
model.fit(X_train, y_train)

# Save to persistent directory (NOT temp dir)
model_dir = Path("data/models")
model_dir.mkdir(parents=True, exist_ok=True)
model_path = model_dir / f"{model_id}.pkl"
joblib.dump(model, model_path)

# Output path in JSON result
print(json.dumps({"model_path": str(model_path), ...}))
```

The sandbox's PYTHONPATH includes the project root, so `data/models/` resolves to the project's `data/models/` directory — not a temp path.

### Strategy Persistence

Generated Strategy classes are saved to `data/strategies/`:

```
data/
  models/               # Trained model files (.pkl, .pt)
    transformer_abc123.pt
    gbm_def456.pkl
  strategies/            # Generated Strategy class files (.py)
    transformer_abc123.py
    gbm_def456.py
  playbook.jsonl         # Knowledge store
  quantclaw.db           # SQLite state
```

The Trainer returns both `model_path` and `strategy_path` in its result. The Backtester can load the strategy from `strategy_path`.

### Strategy Code Generation

The Strategy class references the persisted model:

```python
class Strategy:
    name = "transformer_momentum_vol"
    description = "Transformer on momentum_5d + vol_20d"
    universe = ["AAPL", "MSFT", ...]
    frequency = "weekly"
    _model_path = "data/models/transformer_abc123.pt"
    _model_type = "transformer"

    def signals(self, data):
        model = self._load_model()
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=60)
            if len(df) < 20:
                continue
            momentum_5d = float(df["close"].pct_change(5).iloc[-1])
            vol_20d = float(df["close"].rolling(20).std().iloc[-1])
            score = float(model.predict([[momentum_5d, vol_20d]])[0])
            scores[symbol] = score
        return scores

    def allocate(self, scores, portfolio):
        ranked = sorted(scores, key=scores.get, reverse=True)[:5]
        return {s: 1/len(ranked) for s in ranked}

    def _load_model(self):
        import joblib
        return joblib.load(self._model_path)
```

For PyTorch models, `_load_model` uses `torch.load()` instead. The Trainer generates the appropriate loading code based on model type.

### Training Script Generator (model_trainer.py)

`quantclaw/sandbox/model_trainer.py` generates complete training scripts for sandbox execution:

```python
# quantclaw/sandbox/model_trainer.py
# Generates Python scripts that run inside the sandbox
#
# Input: factors, symbols, model_type, model_params, forward_period, data paths
# Output: a Python script string that:
#   1. Loads data from parquet files
#   2. Computes features from factor code
#   3. Creates labels (forward returns)
#   4. Train/test splits (walk-forward)
#   5. Trains the model
#   6. Evaluates out-of-sample
#   7. Saves model to data/models/
#   8. Prints metrics as JSON to stdout
```

The Trainer calls `generate_training_script(...)` to get the script, then sends it to `Sandbox.execute_code()`.

## Researcher Collaboration Patterns

The Researcher is the knowledge bridge — connects external information to every agent. All interactions mediated through the Scheduler (no direct agent-to-agent communication).

### Researcher Implementation

The Researcher uses LLM calls (most capable model) to synthesize web search results. Its `execute()` method:
1. Receives a structured task (topic, context, what to look for)
2. Calls `web_search()` with relevant queries
3. Calls the LLM to synthesize findings into structured output
4. Returns structured findings that downstream agents can act on

### Researcher Task Types

The Researcher accepts different task types via the `task` field:

```python
# Factor research (for Miner)
{"task": "search_factors", "topic": "momentum alpha", "context": "equity markets"}

# Model research (for Trainer)
{"task": "search_models", "topic": "gradient boosting alternatives", "context": "factor models"}

# Risk research (for Risk Monitor)
{"task": "search_risks", "topic": "tech sector concentration", "context": "portfolio has 60% tech"}

# Event research (for Sentinel)
{"task": "search_events", "topic": "AAPL dropped 5%", "context": "sudden price move"}

# Data source research (for Ingestor)
{"task": "search_data_sources", "topic": "earnings surprise data", "context": "need fundamental data"}

# Regulation research (for Compliance)
{"task": "search_regulations", "topic": "short selling rules", "context": "entering new market"}
```

Each task type produces a structured output format with `findings`, `suggested_factors`, `suggested_models`, or `suggested_data_sources` as appropriate.

### Researcher Output Structure

```python
AgentResult(status=SUCCESS, data={
    "findings": [
        {"topic": "LightGBM with target encoding",
         "source": "arxiv.org/abs/...",
         "relevance": "high",
         "recommendation": "Try LightGBM with target_encoder=True",
         "model_params": {"n_estimators": 500, "learning_rate": 0.05}},
    ],
    "suggested_factors": ["earnings_surprise", "analyst_revision"],
    "suggested_models": ["lightgbm", "ridge_regression"],
    "suggested_data_sources": [],
})
```

### Collaboration Matrix

| Agent | Trigger | Researcher does | Frequency |
|---|---|---|---|
| **Miner** | Scheduler exploring new factors | Search papers, suggest hypotheses | Per exploration cycle |
| **Trainer** | Scheduler trying new model types | Search ML techniques, recommend params | When iterating on models |
| **Risk Monitor** | Flags unusual exposure | Search for contextual risks/events | On-demand via Scheduler |
| **Sentinel** | Unusual price/volume detected | Search for what caused the move | On-demand via Scheduler |
| **Ingestor** | Agent reports missing data type | Search for data source APIs | On-demand, recorded to Playbook |
| **Backtester** | Scheduler wants realistic simulation | Search for cost models, microstructure | On-demand |
| **Compliance** | New trade type or market entered | Search for applicable regulations | On-demand |

Note: Risk Monitor, Sentinel, and other agents don't directly request research. The Scheduler sees their output, decides research is needed, and adds a Researcher step to the next DAG. All mediated through the Scheduler.

### Data Flow: Miner → Trainer via _upstream_results

When the Scheduler composes a DAG with Miner (step 2) feeding into Trainer (step 3), the data flows through the Dispatcher's `_upstream_results` mechanism:

```
DAG:
  Step 0: Researcher → returns {findings, suggested_factors}
  Step 1: Ingestor   → returns {ohlcv: {AAPL: {...}, MSFT: {...}}}
  Step 2: Miner      → receives _upstream_results["0"] (Researcher) + ["1"] (Ingestor)
                     → returns {factors: [{name, code, metrics, ...}]}
  Step 3: Trainer    → receives _upstream_results["2"] (Miner)
                     → extracts factors from _upstream_results["2"]["factors"]
                     → trains model, returns {strategy_code, metrics}
  Step 4: Backtester → receives _upstream_results["3"] (Trainer)
                     → loads strategy from strategy_path, evaluates
```

The Trainer automatically detects and extracts factors from upstream results:

```python
# In Trainer.execute()
factors = task.get("factors", [])
if not factors and "_upstream_results" in task:
    for upstream in task["_upstream_results"].values():
        if isinstance(upstream, dict) and "factors" in upstream:
            factors = upstream["factors"]
            break
```

### Example DAGs the Scheduler generates

**Research-first discovery:**
```
Step 0: Researcher — "latest alpha factor approaches 2024-2025"  [LLM]
Step 1: Ingestor — fetch data for universe [code-only, parallel with 0]
Step 2: Miner — discover factors using Researcher suggestions + data [LLM, depends: 0, 1]
Step 3: Trainer — build model from best factors [code-only, depends: 2]
Step 4: Backtester — evaluate strategy in sandbox [code-only, depends: 3]
```

**Model improvement:**
```
Step 0: Researcher — "alternatives to gradient boosting for factor models" [LLM]
Step 1: Trainer — try recommended model type [code-only, depends: 0]
Step 2: Backtester — evaluate [code-only, depends: 1]
```

**Failure recovery:**
```
Step 0: Researcher — "non-momentum alpha sources in current regime" [LLM]
Step 1: Miner — explore suggestions [LLM, depends: 0]
```

These DAGs are generated by template matching (for known patterns) or the Planner LLM (for novel requests). See [Workflow Efficiency design](2026-04-06-workflow-efficiency-design.md) for template details.

## What Changes

| File | Change |
|---|---|
| Modify: `quantclaw/agents/miner.py` | Full implementation with evolutionary loop, LLM hypothesis generation |
| Modify: `quantclaw/agents/trainer.py` | Full implementation with ML pipeline, code-only execution, dependency validation, custom model validation |
| Modify: `quantclaw/agents/researcher.py` | Enhance with structured task types, LLM synthesis of web search results |
| Create: `quantclaw/sandbox/factor_evaluator.py` | Factor evaluation metrics (IC, Rank IC, turnover, Sharpe) |
| Create: `quantclaw/sandbox/model_trainer.py` | Training script generator for sandbox execution |
| Create: `data/models/` | Directory for persisted trained models |
| Create: `data/strategies/` | Directory for generated Strategy class files |
| Create: `tests/test_miner.py` | Miner agent tests |
| Create: `tests/test_trainer.py` | Trainer agent tests |
| Create: `tests/test_factor_evaluator.py` | Factor evaluation tests |
| Create: `tests/test_researcher_structured.py` | Researcher structured output tests |

## Non-Changes

- Sandbox infrastructure — already built, Miner/Trainer use `execute_code()`
- Playbook — already has FACTOR_LIBRARY entry type
- Scheduler — already has iterative intelligence, composes DAGs with these agents
- Backtester — already evaluates Strategy classes in sandbox
- Dispatcher — already injects `_upstream_results` between dependent steps
- Event types — existing events sufficient
