"""YAML config loader with defaults and env var expansion."""
from __future__ import annotations
import os
import re
import yaml
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).parent / "default.yaml"

def _expand_env_vars(obj):
    if isinstance(obj, str):
        return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    return obj

def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config(override_path: str = None) -> dict:
    with open(DEFAULT_CONFIG) as f:
        config = yaml.safe_load(f)

    if override_path and Path(override_path).exists():
        with open(override_path) as f:
            override = yaml.safe_load(f) or {}
        config = _deep_merge(config, override)

    return _expand_env_vars(config)
