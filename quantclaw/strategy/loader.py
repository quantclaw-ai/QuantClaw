"""Load user strategy files."""
from __future__ import annotations
import importlib.util
from pathlib import Path


def load_strategy(path: str):
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")
    spec = importlib.util.spec_from_file_location("user_strategy", str(file_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Strategy"):
        raise ValueError(f"Strategy file must define a 'Strategy' class: {path}")
    strategy = module.Strategy()
    if not hasattr(strategy, "signals"):
        raise ValueError("Strategy must implement signals(self, data) method")
    if not hasattr(strategy, "allocate"):
        raise ValueError("Strategy must implement allocate(self, scores, portfolio) method")
    return strategy


def list_templates(category: str = None) -> list[dict]:
    template_dir = Path(__file__).parent / "templates"
    templates = []
    categories = [category] if category else ["beginner", "intermediate", "advanced", "options", "baselines"]
    for cat in categories:
        cat_dir = template_dir / cat
        if not cat_dir.exists():
            continue
        for f in sorted(cat_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            templates.append({"name": f.stem, "category": cat, "path": str(f)})
    return templates
