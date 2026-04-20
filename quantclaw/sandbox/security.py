"""AST import validation and environment stripping."""
from __future__ import annotations

import ast
from dataclasses import dataclass


ALLOWED_IMPORTS = frozenset({
    "math", "statistics", "datetime", "time", "json", "re", "collections",
    "itertools", "functools", "decimal", "fractions", "typing", "warnings",
    "os", "sys", "pathlib",
    "numpy", "pandas", "scipy", "sklearn", "statsmodels", "joblib",
    "xgboost", "lightgbm",
    "np", "pd",
    # quantclaw modules are considered trusted — the sandbox's PYTHONPATH
    # exposes them, and system-generated runners (model_trainer, engine_builtin)
    # import from them. They cannot escape the subprocess.
    "quantclaw",
})

# Names that, if referenced in the AST, are treated as a security violation.
# Dunder attributes are blocked because they are the standard escape path from
# a restricted namespace (e.g. `().__class__.__mro__[1].__subclasses__()`).
BLOCKED_BUILTINS = frozenset({
    "__import__", "exec", "eval", "compile",
    "getattr", "setattr", "delattr",
    "globals", "locals", "vars",
})

BLOCKED_DUNDER_ATTRS = frozenset({
    "__class__", "__bases__", "__mro__", "__subclasses__",
    "__globals__", "__builtins__", "__import__",
    "__dict__", "__getattribute__", "__getattr__",
    "__code__", "__closure__",
})

SENSITIVE_ENV_PATTERNS = frozenset({
    "KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH",
    "API", "PRIVATE", "CERT", "COOKIE", "SESSION", "OAUTH",
})


@dataclass(frozen=True)
class ImportWarning:
    module: str
    line: int
    message: str
    critical: bool = False


def validate_imports(code: str) -> list[ImportWarning]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    warnings: list[ImportWarning] = []

    for node in ast.walk(tree):
        # Imports: whitelist enforced. Any non-allowed module is critical.
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module not in ALLOWED_IMPORTS:
                    warnings.append(ImportWarning(
                        module=root_module,
                        line=node.lineno,
                        message=f"Import '{alias.name}' is not in the allowed list",
                        critical=True,
                    ))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module not in ALLOWED_IMPORTS:
                    warnings.append(ImportWarning(
                        module=root_module,
                        line=node.lineno,
                        message=f"Import from '{node.module}' is not in the allowed list",
                        critical=True,
                    ))

        # Direct calls to blocked builtins.
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_BUILTINS:
                warnings.append(ImportWarning(
                    module=func.id,
                    line=node.lineno,
                    message=f"Builtin '{func.id}()' is not allowed in sandboxed code",
                    critical=True,
                ))

        # Dunder attribute access — classic Python sandbox-escape path.
        elif isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_DUNDER_ATTRS:
                warnings.append(ImportWarning(
                    module=node.attr,
                    line=node.lineno,
                    message=f"Access to dunder attribute '{node.attr}' is not allowed",
                    critical=True,
                ))

    return warnings


def strip_env(env: dict[str, str] | None = None) -> dict[str, str]:
    import os
    source = env if env is not None else dict(os.environ)
    return {
        k: v for k, v in source.items()
        if not any(pattern in k.upper() for pattern in SENSITIVE_ENV_PATTERNS)
    }
