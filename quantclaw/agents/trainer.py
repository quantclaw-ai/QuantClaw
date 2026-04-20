"""Trainer: ML model training pipeline.

Code-only agent -- no LLM calls. The Scheduler/Researcher decide model type
and hyperparameters. The Trainer executes the mechanical pipeline:
feature engineering -> train -> evaluate -> save -> generate Strategy class.
All training runs in the sandbox.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

MODEL_REQUIREMENTS: dict[str, list[str]] = {
    "gradient_boosting": ["sklearn"],
    "random_forest": ["sklearn"],
    "ridge": ["sklearn"],
    "linear": ["sklearn"],
    "lasso": ["sklearn"],
    "elasticnet": ["sklearn"],
    "xgboost": ["xgboost"],
    "lightgbm": ["lightgbm"],
    "svm": ["sklearn"],
    "knn": ["sklearn"],
    "adaboost": ["sklearn"],
    "extratrees": ["sklearn"],
    "lstm": ["torch"],
    "transformer": ["torch"],
    "tcn": ["torch"],
    "gru": ["torch"],
    "timefm": ["torch", "transformers"],
    "chronos": ["torch"],
    "prophet": ["prophet"],
}


class TrainerAgent(BaseAgent):
    name = "trainer"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        # Normalize model type aliases (LLMs generate inconsistent names)
        _MODEL_ALIASES = {
            "elastic_net": "elasticnet",
            "elastic net": "elasticnet",
            "gbm": "gradient_boosting",
            "gbt": "gradient_boosting",
            "gbdt": "gradient_boosting",
            "rf": "random_forest",
            "logistic": "linear",
            "logistic_regression": "linear",
            "lgbm": "lightgbm",
            "xgb": "xgboost",
            "svc": "svm",
            "support_vector": "svm",
            "support_vector_machine": "svm",
            "extra_trees": "extratrees",
            "ada_boost": "adaboost",
            "k_nearest": "knn",
            "kneighbors": "knn",
        }
        model_type = task.get("model_type", "gradient_boosting")
        model_type = _MODEL_ALIASES.get(model_type.lower(), model_type)
        model_params = task.get("model_params", {})
        symbols = task.get("symbols", [])
        forward_period = task.get("forward_period", 5)

        factors = self._extract_factors(task)

        if not factors:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="No factors provided. Pass factors directly or via upstream Miner step.",
            )

        missing = self._check_dependencies(model_type)
        if missing:
            return AgentResult(
                status=AgentStatus.FAILED,
                error=f"Model type '{model_type}' requires: pip install {' '.join(missing)}",
            )

        if model_type == "custom":
            error = self._validate_custom_model(
                task.get("model_path", ""), task.get("model_class", "")
            )
            if error:
                return AgentResult(status=AgentStatus.FAILED, error=error)

        model_id = f"{model_type}_{uuid.uuid4().hex[:8]}"

        try:
            from quantclaw.sandbox.model_trainer import generate_training_script, UnknownModelType
            from quantclaw.sandbox.sandbox import Sandbox

            try:
                script = generate_training_script(
                    factors=factors,
                    symbols=symbols,
                    model_type=model_type,
                    model_params=model_params,
                    model_id=model_id,
                    forward_period=forward_period,
                )
            except UnknownModelType:
                # LLM fallback: generate training script dynamically
                logger.info("Unknown model type '%s', generating script via LLM", model_type)
                script = await self._generate_dynamic_script(
                    model_type=model_type,
                    model_params=model_params,
                    model_id=model_id,
                    factors=factors,
                    symbols=symbols,
                    forward_period=forward_period,
                )
                if not script:
                    return AgentResult(
                        status=AgentStatus.FAILED,
                        error=f"Failed to generate training script for '{model_type}' via LLM",
                    )

            sandbox = Sandbox(config=self._config)
            timeout = self._config.get("sandbox", {}).get("timeout", 60)

            # Fetch data for sandbox
            dataframes = await self._fetch_data(symbols, task)
            data_summary = self._summarize_dataframes(dataframes)

            result = await sandbox.execute_code(script, timeout=timeout, data=dataframes)

            if result.status == "ok" and result.result:
                data = result.result
                if "error" in data:
                    return AgentResult(status=AgentStatus.FAILED, error=data["error"])

                strategy_code = self._generate_strategy(data, factors, symbols, model_type)
                data["strategy_code"] = strategy_code

                strategy_path = self._save_strategy(model_id, strategy_code)
                if strategy_path:
                    data["strategy_path"] = strategy_path
                if data_summary:
                    data["training_data_window"] = data_summary

                return AgentResult(status=AgentStatus.SUCCESS, data=data)
            elif result.status == "timeout":
                return AgentResult(status=AgentStatus.FAILED, error="Training timed out")
            else:
                full_error = result.stderr or "Training failed"
                logger.error("Trainer sandbox failed:\n%s", full_error[:2000])
                return AgentResult(
                    status=AgentStatus.FAILED,
                    error=full_error[:1000],
                )
        except ValueError as e:
            return AgentResult(status=AgentStatus.FAILED, error=str(e))
        except Exception:
            logger.exception("Trainer execution failed")
            return AgentResult(status=AgentStatus.FAILED, error="Trainer execution failed")

    async def _generate_dynamic_script(
        self, model_type: str, model_params: dict, model_id: str,
        factors: list[dict], symbols: list[str], forward_period: int,
    ) -> str | None:
        """Use LLM to generate a training script for an unknown model type.

        The LLM writes the import + ModelClass definition. The rest of the
        script (data loading, feature engineering, train/test split, evaluation,
        model save) uses our standard template to ensure consistent output format.
        """
        try:
            from quantclaw.execution.router import LLMRouter
            router = LLMRouter(self._config)

            prompt = (
                f"Generate a Python import statement and class for model type '{model_type}' "
                f"that can be used for binary classification.\n\n"
                f"Requirements:\n"
                f"- Import from a well-known Python ML library (sklearn, xgboost, lightgbm, etc.)\n"
                f"- The result must define `ModelClass` — a class with fit(X, y) and predict(X) methods\n"
                f"- If the model needs predict_proba, it should support it\n"
                f"- Model params to apply: {json.dumps(model_params) if model_params else '{}'}\n\n"
                f"Return ONLY the Python code (import + class definition), no markdown, no explanation.\n"
                f"Example output:\n"
                f"from sklearn.svm import SVC as ModelClass\n\n"
                f"Or for models needing wrapping:\n"
                f"from sklearn.svm import SVC as _Base\n"
                f"class ModelClass(_Base):\n"
                f"    def __init__(self, **kw):\n"
                f"        kw.setdefault('probability', True)\n"
                f"        super().__init__(**kw)"
            )

            response = await router.call(
                self.name,
                messages=[{"role": "user", "content": prompt}],
                system="You are a machine learning engineer. Generate minimal, correct Python import code.",
                temperature=0.2,
            )

            # Clean up response — strip markdown fences if present
            import_code = response.strip()
            if import_code.startswith("```"):
                lines = import_code.split("\n")
                import_code = "\n".join(
                    l for l in lines if not l.startswith("```")
                ).strip()

            # Validate it's actually Python by trying to compile
            compile(import_code, "<dynamic_model>", "exec")

            # Build the full training script using our standard template
            # but with the LLM-generated import
            from quantclaw.sandbox.model_trainer import generate_training_script, MODEL_IMPORTS

            # Temporarily register the dynamic import and generate
            MODEL_IMPORTS[model_type] = import_code
            try:
                script = generate_training_script(
                    factors=factors,
                    symbols=symbols,
                    model_type=model_type,
                    model_params=model_params,
                    model_id=model_id,
                    forward_period=forward_period,
                )
            finally:
                # Don't persist — let it re-generate next time for safety
                MODEL_IMPORTS.pop(model_type, None)

            logger.info("Generated dynamic training script for '%s'", model_type)
            return script

        except SyntaxError as e:
            logger.warning("LLM generated invalid Python for '%s': %s", model_type, e)
            return None
        except Exception:
            logger.exception("Dynamic script generation failed for '%s'", model_type)
            return None

    async def _fetch_data(self, symbols: list[str], task: dict) -> dict:
        """Fetch DataFrames for sandbox training."""
        from quantclaw.agents.market_data import load_market_data

        if not symbols:
            return {}

        start = task.get("start") or None
        end = task.get("end") or datetime.now(timezone.utc).date().isoformat()
        extra_fields = self._extract_extra_fields_from_upstream(task)

        try:
            bundle = load_market_data(
                self._config,
                symbols,
                start,
                end,
                extra_fields=extra_fields,
            )
            return bundle.frames
        except Exception:
            logger.exception("Data plugin initialization failed")
            return {}

    def _summarize_dataframes(self, dataframes: dict) -> dict:
        if not dataframes:
            return {}

        windows = {}
        starts = []
        ends = []
        for symbol, df in dataframes.items():
            if df is None or df.empty:
                continue
            start = str(df.index.min().date()) if hasattr(df.index.min(), "date") else str(df.index.min())
            end = str(df.index.max().date()) if hasattr(df.index.max(), "date") else str(df.index.max())
            windows[symbol] = {"start": start, "end": end, "rows": len(df)}
            starts.append(start)
            ends.append(end)

        if not windows:
            return {}

        common_start = max(starts) if starts else ""
        common_end = min(ends) if ends else ""
        return {
            "per_symbol": windows,
            "common_start": common_start,
            "common_end": common_end,
        }

    def _validate_factor_code(self, factors: list[dict]) -> list[dict]:
        """Filter out factors with invalid Python syntax."""
        import ast
        valid = []
        for f in factors:
            code = f.get("code", "")
            if not code:
                continue
            try:
                # Try to parse as an expression
                ast.parse(code, mode="eval")
                valid.append(f)
            except SyntaxError:
                logger.warning("Skipping factor '%s' — invalid syntax: %s",
                               f.get("name", "?"), code[:100])
        return valid

    def _extract_factors(self, task: dict) -> list[dict]:
        factors = task.get("factors", [])
        if factors:
            return self._validate_factor_code(factors)
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict) and "factors" in data:
                return self._validate_factor_code(data["factors"])
        return []

    def _extract_extra_fields_from_upstream(self, task: dict) -> list[str]:
        base = {"open", "high", "low", "close", "volume"}
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict) and "columns" in data:
                columns = data["columns"]
                if isinstance(columns, list):
                    return [column for column in columns if column not in base]
        return []

    def _check_dependencies(self, model_type: str) -> list[str]:
        missing = []
        for pkg in MODEL_REQUIREMENTS.get(model_type, []):
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)
        return missing

    def _validate_custom_model(self, model_path: str, model_class: str) -> str | None:
        from pathlib import Path
        import importlib.util

        path = Path(model_path)
        if not path.exists():
            return f"Custom model file not found: {model_path}"
        try:
            spec = importlib.util.spec_from_file_location("custom_model", str(path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            return f"Failed to load custom model: {e}"
        cls = getattr(module, model_class, None)
        if cls is None:
            return f"Class '{model_class}' not found in {model_path}"
        required = ["fit", "predict", "save", "load"]
        missing = [m for m in required if not callable(getattr(cls, m, None))]
        if missing:
            return f"Custom model missing methods: {missing}"
        return None

    def _generate_strategy(
        self, training_result: dict, factors: list[dict],
        symbols: list[str], model_type: str,
    ) -> str:
        from quantclaw.agents.market_data import (
            BASE_OHLCV_COLUMNS,
            extract_required_columns_from_code,
        )

        model_path = training_result.get("model_path", "")
        model_id = training_result.get("model_id", "unknown")
        features = training_result.get("features_used", [f["name"] for f in factors])
        required_columns: list[str] = []
        seen_columns: set[str] = set()
        for factor in factors:
            for column in extract_required_columns_from_code(factor.get("code", "")):
                if column not in seen_columns:
                    seen_columns.add(column)
                    required_columns.append(column)
        extra_fields = [column for column in required_columns if column not in BASE_OHLCV_COLUMNS]

        feature_code_lines = []
        for f, name in zip(factors, features):
            if "code" in f:
                feature_code_lines.append(
                    f'                {name} = float(({f["code"]}).iloc[-1])'
                )

        feature_code = "\n".join(feature_code_lines) if feature_code_lines else "                pass"
        feature_list = ", ".join(features)
        model_path_safe = model_path.replace("\\", "/")

        # Store absolute path for sandbox to copy model file into temp dir.
        # Strategy code uses a relative path that the sandbox populates.
        from pathlib import Path
        abs_model_path = str(Path(model_path_safe).resolve()).replace("\\", "/")
        model_filename = Path(abs_model_path).name

        return f'''class Strategy:
    name = "{model_type}_{model_id}"
    description = "{model_type} on {feature_list}"
    universe = {json.dumps(symbols)}
    frequency = "weekly"
    required_columns = {json.dumps(required_columns)}
    _extra_fields = {json.dumps(extra_fields)}
    # Absolute path — used by sandbox to copy model into temp dir
    _model_src_path = "{abs_model_path}"
    # Relative path — used at runtime inside the sandbox
    _model_path = "models/{model_filename}"

    def signals(self, data):
        import joblib
        from pathlib import Path as _P
        # Try relative (sandbox) path first, fall back to absolute (src) path
        _mp = self._model_path if _P(self._model_path).exists() else self._model_src_path
        model = joblib.load(_mp)
        scores = {{}}
        self._last_signal_errors = []
        for symbol in self.universe:
            df = data.history(symbol, bars=60)
            if len(df) < 20:
                continue
            try:
{feature_code}
                features = [[{feature_list}]]
                # Use predict_proba for continuous scores (probability of up move)
                # Falls back to predict() for models without predict_proba
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(features)[0]
                    scores[symbol] = float(proba[1]) if len(proba) > 1 else float(proba[0])
                else:
                    scores[symbol] = float(model.predict(features)[0])
            except Exception as exc:
                self._last_signal_errors.append({{"symbol": symbol, "error": str(exc)}})
        return scores

    def allocate(self, scores, portfolio):
        if not scores:
            return {{}}
        ranked = sorted(scores, key=scores.get, reverse=True)[:5]
        return {{s: 1/len(ranked) for s in ranked}}
'''

    def _save_strategy(self, model_id: str, strategy_code: str) -> str | None:
        from pathlib import Path
        try:
            strategy_dir = Path("data/strategies")
            strategy_dir.mkdir(parents=True, exist_ok=True)
            path = strategy_dir / f"{model_id}.py"
            path.write_text(strategy_code, encoding="utf-8")
            return str(path)
        except Exception:
            logger.exception("Failed to save strategy")
            return None
