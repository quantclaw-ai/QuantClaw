"""Training script generator for sandbox execution."""
from __future__ import annotations

import json

MODEL_IMPORTS = {
    "gradient_boosting": "from sklearn.ensemble import GradientBoostingClassifier as ModelClass",
    "random_forest": "from sklearn.ensemble import RandomForestClassifier as ModelClass",
    "ridge": "from sklearn.linear_model import RidgeClassifier as ModelClass",
    "linear": "from sklearn.linear_model import LogisticRegression as ModelClass",
    "lasso": (
        "from sklearn.linear_model import LogisticRegression as _LR\n"
        "class ModelClass(_LR):\n"
        "    def __init__(self, **kw):\n"
        "        kw.setdefault('penalty', 'l1')\n"
        "        kw.setdefault('solver', 'saga')\n"
        "        kw.setdefault('max_iter', 1000)\n"
        "        super().__init__(**kw)"
    ),
    "elasticnet": (
        "from sklearn.linear_model import LogisticRegression as _LR\n"
        "class ModelClass(_LR):\n"
        "    def __init__(self, **kw):\n"
        "        kw.setdefault('penalty', 'elasticnet')\n"
        "        kw.setdefault('solver', 'saga')\n"
        "        kw.setdefault('l1_ratio', 0.5)\n"
        "        kw.setdefault('max_iter', 1000)\n"
        "        super().__init__(**kw)"
    ),
    "xgboost": "from xgboost import XGBClassifier as ModelClass",
    "lightgbm": "from lightgbm import LGBMClassifier as ModelClass",
    "svm": "from sklearn.svm import SVC as ModelClass",
    "knn": "from sklearn.neighbors import KNeighborsClassifier as ModelClass",
    "adaboost": "from sklearn.ensemble import AdaBoostClassifier as ModelClass",
    "extratrees": "from sklearn.ensemble import ExtraTreesClassifier as ModelClass",
}

ADVANCED_MODELS = {"lstm", "transformer", "tcn", "gru", "timefm", "chronos", "prophet"}


class UnknownModelType(Exception):
    """Raised when a model type isn't in the hardcoded registry.

    The Trainer catches this and falls back to LLM-generated training code.
    """
    def __init__(self, model_type: str):
        self.model_type = model_type
        super().__init__(f"Unknown model type: {model_type}")


def generate_training_script(
    factors: list[dict],
    symbols: list[str],
    model_type: str,
    model_params: dict,
    model_id: str,
    forward_period: int = 5,
) -> str:
    """Generate a complete training script for sandbox execution."""
    if model_type in ADVANCED_MODELS:
        return _generate_advanced_script(model_type)

    if model_type not in MODEL_IMPORTS:
        # Unknown model — signal to Trainer to use LLM-generated script
        raise UnknownModelType(model_type)

    import_line = MODEL_IMPORTS[model_type]

    # Apply baseline regularization defaults to prevent overfitting.
    # User-provided model_params override these defaults.
    _regularization_defaults: dict[str, dict] = {
        "gradient_boosting": {"max_depth": 3, "n_estimators": 100, "learning_rate": 0.05, "min_samples_leaf": 20, "subsample": 0.8},
        "random_forest": {"max_depth": 5, "n_estimators": 100, "min_samples_leaf": 10, "max_features": "sqrt"},
        "xgboost": {"max_depth": 3, "n_estimators": 100, "learning_rate": 0.05, "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 1.0, "use_label_encoder": False, "eval_metric": "logloss"},
        "lightgbm": {"max_depth": 3, "n_estimators": 100, "learning_rate": 0.05, "min_child_samples": 20, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 1.0, "verbosity": -1},
        "adaboost": {"n_estimators": 50, "learning_rate": 0.1},
        "extratrees": {"max_depth": 5, "n_estimators": 100, "min_samples_leaf": 10},
    }
    effective_params = {**_regularization_defaults.get(model_type, {}), **(model_params or {})}
    params_str = json.dumps(effective_params)

    factor_code_blocks = []
    factor_names = []
    for f in factors:
        name = f["name"]
        code = f["code"]
        factor_names.append(name)
        factor_code_blocks.append(f'    features["{name}"] = {code}')

    features_code = "\n".join(factor_code_blocks) if factor_code_blocks else '    pass'
    symbols_str = json.dumps(symbols)
    factor_names_str = json.dumps(factor_names)

    return f'''import pandas as pd
import numpy as np
import json
import joblib
from pathlib import Path

{import_line}

# Load data
data = {{}}
data_dir = Path("data")
if data_dir.exists():
    for f in data_dir.glob("*.parquet"):
        data[f.stem] = pd.read_parquet(f)

symbols = {symbols_str}
forward_period = {forward_period}
model_id = "{model_id}"
model_params = {params_str}

# Compute features for each symbol
all_features = []
all_labels = []
all_labels_raw = []

for symbol in symbols:
    if symbol not in data:
        continue
    df = data[symbol]
    if len(df) < 60:
        continue

    features = {{}}
{features_code}

    # Forward returns
    fwd_ret = df["close"].pct_change(forward_period).shift(-forward_period)

    # Build feature matrix
    feat_df = pd.DataFrame(features, index=df.index)
    feat_df["label"] = (fwd_ret > 0).astype(int)
    feat_df["label_raw"] = fwd_ret
    feat_df = feat_df.dropna()

    if len(feat_df) < 100:
        continue

    all_features.append(feat_df.drop(["label", "label_raw"], axis=1))
    all_labels.append(feat_df["label"])
    all_labels_raw.append(feat_df["label_raw"])

if not all_features:
    print(json.dumps({{"error": "No valid data for training"}}))
    exit(1)

X = pd.concat(all_features)
y = pd.concat(all_labels)
y_raw = pd.concat(all_labels_raw)

# Sort by date for proper time-ordered walk-forward split
sort_idx = X.index.argsort()
X = X.iloc[sort_idx]
y = y.iloc[sort_idx]
y_raw = y_raw.iloc[sort_idx]

# Walk-forward split (80/20, time-ordered)
split = int(len(X) * 0.8)
X_train, X_test = X.iloc[:split], X.iloc[split:]
y_train, y_test = y.iloc[:split], y.iloc[split:]
y_raw_train, y_raw_test = y_raw.iloc[:split], y_raw.iloc[split:]

# Train
model = ModelClass(**model_params)
model.fit(X_train, y_train)

# Evaluate
train_acc = float(model.score(X_train, y_train))
test_acc = float(model.score(X_test, y_test))

# Feature importance (if available)
importance = {{}}
if hasattr(model, "feature_importances_"):
    for i, name in enumerate({factor_names_str}):
        if i < len(model.feature_importances_):
            importance[name] = float(model.feature_importances_[i])
elif hasattr(model, "coef_"):
    coefs = model.coef_.flatten() if model.coef_.ndim > 1 else model.coef_
    for i, name in enumerate({factor_names_str}):
        if i < len(coefs):
            importance[name] = float(abs(coefs[i]))

# Sharpe from actual prediction-weighted forward returns
test_preds = model.predict(X_test)
test_fwd = y_raw_test.values
pred_returns = np.where(test_preds == 1, test_fwd, -test_fwd)
test_sharpe = float(np.mean(pred_returns) / max(np.std(pred_returns), 1e-8) * np.sqrt(252 / max(forward_period, 1)))

train_preds = model.predict(X_train)
train_fwd = y_raw_train.values
train_pred_returns = np.where(train_preds == 1, train_fwd, -train_fwd)
train_sharpe = float(np.mean(train_pred_returns) / max(np.std(train_pred_returns), 1e-8) * np.sqrt(252 / max(forward_period, 1)))

overfit_ratio = train_sharpe / max(abs(test_sharpe), 0.01) if test_sharpe != 0 else 99.0

# Save model to persistent project directory (not temp sandbox dir)
import os as _os
_project_root = _os.environ.get("PYTHONPATH", "").split(_os.pathsep)[0] or "."
model_dir = Path(_project_root) / "data" / "models"
model_dir.mkdir(parents=True, exist_ok=True)
model_path = str(model_dir / f"{{model_id}}.pkl")
joblib.dump(model, model_path)

# Output
print(json.dumps({{
    "model_type": "{model_type}",
    "model_id": model_id,
    "model_path": model_path,
    "features_used": {factor_names_str},
    "feature_importance": importance,
    "sample_size": len(X),
    "metrics": {{
        "train_sharpe": round(train_sharpe, 3),
        "test_sharpe": round(test_sharpe, 3),
        "train_accuracy": round(train_acc, 3),
        "test_accuracy": round(test_acc, 3),
        "overfit_ratio": round(overfit_ratio, 2),
    }},
    "sharpe": round(test_sharpe, 3),
}}))
'''


def _generate_advanced_script(model_type: str) -> str:
    """Generate a script that reports dependency requirements for advanced models."""
    requirements = {
        "lstm": "torch",
        "transformer": "torch",
        "tcn": "torch",
        "gru": "torch",
        "prophet": "prophet",
        "timefm": "transformers",
        "chronos": "chronos-forecasting",
    }
    req = requirements.get(model_type, model_type)
    pkg = req.split("-")[0]

    return f'''import json
import sys

try:
    import {pkg}
except ImportError:
    print(json.dumps({{"error": "Model type '{model_type}' requires: pip install {req}"}}))
    sys.exit(1)

print(json.dumps({{"error": "Advanced model type '{model_type}' training not yet implemented. Use gradient_boosting, random_forest, ridge, xgboost, or lightgbm."}}))
sys.exit(1)
'''
