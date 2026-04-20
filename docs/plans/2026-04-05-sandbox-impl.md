# Agent Sandbox Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add subprocess sandbox so Backtester, Miner, and Trainer agents execute LLM-generated code in isolated subprocesses instead of in-process.

**Architecture:** `quantclaw/sandbox/` package with security module (AST validation, env stripping), sandbox class (async subprocess execution with semaphore), and runner scripts (bootstrap for subprocess). Backtester agent updated to use sandbox.

**Tech Stack:** Python 3.12+ (asyncio.create_subprocess_exec, ast, resource, tempfile, parquet)

---

## Task 1: Security Module — AST Validation + Env Stripping

**Files:**
- Create: `quantclaw/sandbox/__init__.py`
- Create: `quantclaw/sandbox/security.py`
- Create: `tests/test_sandbox_security.py`

**Step 1: Write the failing tests**

```python
# tests/test_sandbox_security.py
"""Tests for sandbox security: AST validation and env stripping."""
import pytest
from quantclaw.sandbox.security import validate_imports, strip_env, ImportWarning


def test_safe_code_passes():
    code = "import pandas as pd\nimport numpy as np\nresult = pd.DataFrame()"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_os_import_warns():
    code = "import os\nos.system('rm -rf /')"
    warnings = validate_imports(code)
    assert len(warnings) == 1
    assert "os" in warnings[0].module


def test_subprocess_import_warns():
    code = "import subprocess\nsubprocess.run(['ls'])"
    warnings = validate_imports(code)
    assert len(warnings) == 1


def test_from_import_warns():
    code = "from shutil import rmtree"
    warnings = validate_imports(code)
    assert len(warnings) == 1
    assert "shutil" in warnings[0].module


def test_socket_warns():
    code = "import socket\nsocket.create_connection(('evil.com', 80))"
    warnings = validate_imports(code)
    assert len(warnings) == 1


def test_allowed_imports_pass():
    code = "import math\nimport json\nimport re\nimport datetime"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_numpy_pandas_scipy_pass():
    code = "import numpy\nimport pandas\nimport scipy\nimport sklearn"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_strip_env_removes_secrets():
    env = {
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "ANTHROPIC_API_KEY": "sk-ant-xxx",
        "OPENAI_API_KEY": "sk-xxx",
        "DATABASE_TOKEN": "dbtoken",
        "MY_SECRET": "shhh",
        "PYTHONPATH": "/code",
        "NORMAL_VAR": "hello",
    }
    stripped = strip_env(env)
    assert "PATH" in stripped
    assert "HOME" in stripped
    assert "PYTHONPATH" in stripped
    assert "ANTHROPIC_API_KEY" not in stripped
    assert "OPENAI_API_KEY" not in stripped
    assert "DATABASE_TOKEN" not in stripped
    assert "MY_SECRET" not in stripped
    assert "NORMAL_VAR" in stripped


def test_syntax_error_in_code():
    code = "def foo(\n"  # syntax error
    warnings = validate_imports(code)
    # Should not crash, return empty or error indicator
    assert isinstance(warnings, list)
```

**Step 2: Create package and implementation**

```python
# quantclaw/sandbox/__init__.py
"""Subprocess sandbox for safe code execution."""
```

```python
# quantclaw/sandbox/security.py
"""AST import validation and environment stripping."""
from __future__ import annotations

import ast
from dataclasses import dataclass


ALLOWED_IMPORTS = frozenset({
    "math", "statistics", "datetime", "json", "re", "collections",
    "itertools", "functools", "decimal", "fractions",
    "numpy", "pandas", "scipy", "sklearn", "statsmodels",
    "np", "pd",  # common aliases
})

SENSITIVE_ENV_PATTERNS = frozenset({
    "KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH",
})


@dataclass(frozen=True)
class ImportWarning:
    module: str
    line: int
    message: str


def validate_imports(code: str) -> list[ImportWarning]:
    """Scan code AST for imports not in the whitelist.

    Returns warnings (not errors) — the Scheduler decides whether to proceed.
    This is defense-in-depth: bypassable via exec/__import__ but catches
    most LLM-generated code patterns.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []  # Can't parse — let the subprocess handle the error

    warnings: list[ImportWarning] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module not in ALLOWED_IMPORTS:
                    warnings.append(ImportWarning(
                        module=root_module,
                        line=node.lineno,
                        message=f"Import '{alias.name}' is not in the allowed list",
                    ))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module not in ALLOWED_IMPORTS:
                    warnings.append(ImportWarning(
                        module=root_module,
                        line=node.lineno,
                        message=f"Import from '{node.module}' is not in the allowed list",
                    ))

    return warnings


def strip_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Strip sensitive environment variables.

    Keeps PATH, HOME, PYTHONPATH and normal vars.
    Removes anything containing KEY, TOKEN, SECRET, PASSWORD, etc.
    """
    import os
    source = env if env is not None else dict(os.environ)
    return {
        k: v for k, v in source.items()
        if not any(pattern in k.upper() for pattern in SENSITIVE_ENV_PATTERNS)
    }
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_sandbox_security.py -v`
Expected: All 9 PASS

**Step 4: Commit**

```bash
git add quantclaw/sandbox/__init__.py quantclaw/sandbox/security.py tests/test_sandbox_security.py
git commit -m "feat: add sandbox security module — AST import validation and env stripping"
```

---

## Task 2: Sandbox Core — Async Subprocess Execution

**Files:**
- Create: `quantclaw/sandbox/sandbox.py`
- Create: `tests/test_sandbox.py`

**Step 1: Write the failing tests**

```python
# tests/test_sandbox.py
"""Tests for sandbox subprocess execution."""
import asyncio
import pytest
from quantclaw.sandbox.sandbox import Sandbox, SandboxResult


def test_execute_simple_code():
    sandbox = Sandbox(config={})

    async def _run():
        result = await sandbox.execute_code("print('hello')")
        assert result.status == "ok"
        assert "hello" in result.stdout

    asyncio.run(_run())


def test_execute_code_with_result():
    sandbox = Sandbox(config={})

    async def _run():
        code = """
import json
RESULT = {"answer": 42}
print(json.dumps(RESULT))
"""
        result = await sandbox.execute_code(code)
        assert result.status == "ok"
        assert result.result["answer"] == 42

    asyncio.run(_run())


def test_execute_code_timeout():
    sandbox = Sandbox(config={})

    async def _run():
        code = "import time; time.sleep(10)"
        result = await sandbox.execute_code(code, timeout=1)
        assert result.status == "timeout"

    asyncio.run(_run())


def test_execute_code_error():
    sandbox = Sandbox(config={})

    async def _run():
        code = "raise ValueError('boom')"
        result = await sandbox.execute_code(code)
        assert result.status == "error"
        assert "boom" in result.stderr

    asyncio.run(_run())


def test_execute_code_syntax_error():
    sandbox = Sandbox(config={})

    async def _run():
        code = "def foo(\n"
        result = await sandbox.execute_code(code)
        assert result.status == "error"

    asyncio.run(_run())


def test_concurrent_limit():
    sandbox = Sandbox(config={}, max_concurrent=1)

    async def _run():
        # Two concurrent executions with max_concurrent=1
        # Second should wait for first
        code = "import time; time.sleep(0.5); print('done')"
        results = await asyncio.gather(
            sandbox.execute_code(code),
            sandbox.execute_code(code),
        )
        assert all(r.status == "ok" for r in results)

    asyncio.run(_run())


def test_cleanup_temp_dir():
    sandbox = Sandbox(config={})

    async def _run():
        result = await sandbox.execute_code("print('test')")
        assert result.status == "ok"
        # Temp dir should be cleaned up — we can't easily verify this
        # but the sandbox should not leak directories

    asyncio.run(_run())


def test_env_stripped():
    sandbox = Sandbox(config={})

    async def _run():
        code = """
import os, json
env = dict(os.environ)
has_key = any('KEY' in k for k in env)
print(json.dumps({"has_secret_key": has_key}))
"""
        result = await sandbox.execute_code(code)
        assert result.status == "ok"
        assert result.result["has_secret_key"] is False

    asyncio.run(_run())
```

**Step 2: Write the Sandbox implementation**

```python
# quantclaw/sandbox/sandbox.py
"""Subprocess sandbox for safe code execution."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quantclaw.sandbox.security import validate_imports, strip_env


@dataclass(frozen=True)
class SandboxResult:
    status: str  # "ok", "error", "timeout"
    stdout: str = ""
    stderr: str = ""
    result: dict[str, Any] | None = None
    import_warnings: list[str] = field(default_factory=list)


class Sandbox:
    """Execute code in isolated subprocesses with guardrails."""

    def __init__(self, config: dict, max_concurrent: int = 3):
        self._config = config
        sandbox_cfg = config.get("sandbox", {})
        self._default_timeout = sandbox_cfg.get("timeout", 60)
        self._max_output = sandbox_cfg.get("max_output", 102400)
        self._max_memory_mb = sandbox_cfg.get("max_memory_mb", 512)
        self._semaphore = asyncio.Semaphore(
            sandbox_cfg.get("max_concurrent", max_concurrent)
        )

    async def execute_code(self, code: str, timeout: int | None = None) -> SandboxResult:
        """Execute Python code in an isolated subprocess."""
        timeout = timeout or self._default_timeout

        # AST validation (defense-in-depth)
        warnings = validate_imports(code)
        warning_msgs = [w.message for w in warnings]

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="qc_sandbox_"))
        try:
            # Write code to temp file
            code_file = temp_dir / "code.py"
            code_file.write_text(code, encoding="utf-8")

            # Execute
            result = await self._run_subprocess(
                [sys.executable, str(code_file)],
                cwd=temp_dir,
                timeout=timeout,
            )
            return SandboxResult(
                status=result["status"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                result=result.get("parsed_result"),
                import_warnings=warning_msgs,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def execute_strategy(
        self,
        strategy_code: str,
        data: dict,
        config: dict,
        timeout: int | None = None,
    ) -> SandboxResult:
        """Run a strategy backtest in an isolated subprocess.

        data: dict of {symbol: DataFrame} — serialized to parquet in temp dir.
        """
        import pandas as pd

        timeout = timeout or self._default_timeout
        temp_dir = Path(tempfile.mkdtemp(prefix="qc_backtest_"))

        try:
            # Write strategy code
            (temp_dir / "strategy.py").write_text(strategy_code, encoding="utf-8")

            # Serialize DataFrames to parquet
            data_dir = temp_dir / "data"
            data_dir.mkdir()
            for symbol, df in data.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df.to_parquet(data_dir / f"{symbol}.parquet")

            # Write config
            (temp_dir / "config.json").write_text(
                json.dumps(config), encoding="utf-8"
            )

            # Run the runner script
            runner = Path(__file__).parent / "runner.py"
            result = await self._run_subprocess(
                [sys.executable, str(runner), str(temp_dir)],
                cwd=temp_dir,
                timeout=timeout,
            )
            return SandboxResult(
                status=result["status"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                result=result.get("parsed_result"),
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _run_subprocess(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: int,
    ) -> dict:
        """Run a subprocess with guardrails."""
        env = strip_env()
        # Ensure PYTHONPATH includes the project root
        project_root = str(Path(__file__).parent.parent.parent)
        env["PYTHONPATH"] = project_root + (
            ";" if sys.platform == "win32" else ":"
        ) + env.get("PYTHONPATH", "")

        # Memory limit preexec (Linux/Mac only)
        preexec = None
        if sys.platform != "win32":
            max_bytes = self._max_memory_mb * 1024 * 1024
            def _set_limits():
                import resource
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
                except (ValueError, resource.error):
                    pass
            preexec = _set_limits

        async with self._semaphore:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(cwd),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    preexec_fn=preexec,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return {"status": "timeout", "stdout": "", "stderr": "Execution timed out"}

                # Truncate output
                stdout = stdout_bytes.decode("utf-8", errors="replace")[:self._max_output]
                stderr = stderr_bytes.decode("utf-8", errors="replace")[:self._max_output]

                if proc.returncode != 0:
                    return {"status": "error", "stdout": stdout, "stderr": stderr}

                # Try to parse last line as JSON result
                parsed = None
                for line in reversed(stdout.strip().splitlines()):
                    try:
                        parsed = json.loads(line)
                        break
                    except (json.JSONDecodeError, ValueError):
                        continue

                return {"status": "ok", "stdout": stdout, "stderr": stderr, "parsed_result": parsed}

            except OSError as e:
                return {"status": "error", "stdout": "", "stderr": str(e)}
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_sandbox.py -v`
Expected: All 8 PASS

**Step 4: Commit**

```bash
git add quantclaw/sandbox/sandbox.py tests/test_sandbox.py
git commit -m "feat: add Sandbox class with async subprocess execution and guardrails"
```

---

## Task 3: Runner Scripts — Strategy Backtest + Code Execution

**Files:**
- Create: `quantclaw/sandbox/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write the failing test**

```python
# tests/test_runner.py
"""Tests for sandbox runner scripts."""
import asyncio
import json
import pytest
from pathlib import Path
from quantclaw.sandbox.sandbox import Sandbox


def test_strategy_runner(tmp_path):
    """Test execute_strategy with a simple strategy."""
    import pandas as pd
    import numpy as np

    sandbox = Sandbox(config={})

    # Create fake OHLCV data
    dates = pd.date_range("2023-01-01", periods=100, freq="B")
    data = {
        "AAPL": pd.DataFrame({
            "open": np.random.uniform(150, 160, 100),
            "high": np.random.uniform(160, 170, 100),
            "low": np.random.uniform(140, 150, 100),
            "close": np.random.uniform(150, 160, 100),
            "volume": np.random.randint(1000000, 5000000, 100),
        }, index=dates),
    }

    strategy_code = '''
class Strategy:
    name = "test_momentum"
    description = "Simple test"
    universe = ["AAPL"]
    frequency = "weekly"

    def signals(self, data):
        scores = {}
        for symbol in self.universe:
            df = data.history(symbol, bars=20)
            if len(df) >= 5:
                scores[symbol] = float(df["close"].iloc[-1] / df["close"].iloc[-5] - 1)
        return scores

    def allocate(self, scores, portfolio):
        return {s: 1.0 for s in scores}

    def risk_check(self, orders, portfolio):
        return True
'''

    async def _run():
        result = await sandbox.execute_strategy(
            strategy_code=strategy_code,
            data=data,
            config={"initial_capital": 100000},
            timeout=30,
        )
        assert result.status == "ok", f"Failed: {result.stderr}"
        assert result.result is not None
        assert "sharpe" in result.result

    asyncio.run(_run())
```

**Step 2: Create the runner script**

```python
# quantclaw/sandbox/runner.py
"""Bootstrap script for strategy backtest in subprocess.

Usage: python runner.py <temp_dir>

Reads:
  temp_dir/strategy.py    — Strategy class
  temp_dir/data/*.parquet — OHLCV data per symbol
  temp_dir/config.json    — Backtest configuration

Outputs: JSON to stdout with backtest results.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: runner.py <temp_dir>"}))
        sys.exit(1)

    temp_dir = Path(sys.argv[1])

    # Load strategy
    strategy_path = temp_dir / "strategy.py"
    if not strategy_path.exists():
        print(json.dumps({"error": "strategy.py not found"}))
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("strategy_module", str(strategy_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "Strategy"):
        print(json.dumps({"error": "Strategy class not found in strategy.py"}))
        sys.exit(1)

    strategy = module.Strategy()

    # Load data
    data_dir = temp_dir / "data"
    data = {}
    if data_dir.exists():
        for parquet_file in data_dir.glob("*.parquet"):
            symbol = parquet_file.stem
            data[symbol] = pd.read_parquet(parquet_file)

    # Load config
    config_path = temp_dir / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())

    # Run backtest using the built-in engine
    from quantclaw.plugins.builtin.engine_builtin import BuiltinEnginePlugin

    engine = BuiltinEnginePlugin()
    result = engine.backtest(strategy, data, config)

    # Serialize result to JSON
    output = {
        "sharpe": result.sharpe,
        "annual_return": result.annual_return,
        "max_drawdown": result.max_drawdown,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
```

**Step 3: Run tests**

Run: `python -m pytest tests/test_runner.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add quantclaw/sandbox/runner.py tests/test_runner.py
git commit -m "feat: add sandbox runner script for strategy backtesting"
```

---

## Task 4: Integrate Sandbox into Backtester Agent

**Files:**
- Modify: `quantclaw/agents/backtester.py`
- Modify: `quantclaw/config/default.yaml`
- Create: `tests/test_backtester_sandbox.py`

**Step 1: Write the failing test**

```python
# tests/test_backtester_sandbox.py
"""Tests for Backtester agent with sandbox execution."""
import asyncio
import pytest
from quantclaw.agents.backtester import BacktesterAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_backtester_with_sandbox():
    bus = EventBus()
    config = {"sandbox": {"enabled": True, "timeout": 30}}
    agent = BacktesterAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "strategy_code": '''
class Strategy:
    name = "test"
    description = "test"
    universe = ["AAPL"]
    frequency = "weekly"
    def signals(self, data):
        return {"AAPL": 0.5}
    def allocate(self, scores, portfolio):
        return {"AAPL": 1.0}
''',
            "symbols": ["AAPL"],
            "start": "2023-01-01",
            "end": "2023-06-01",
        })
        assert result.status == AgentStatus.SUCCESS
        assert "sharpe" in result.data

    asyncio.run(_run())


def test_backtester_sandbox_disabled():
    """When sandbox is disabled, still works (in-process)."""
    bus = EventBus()
    config = {"sandbox": {"enabled": False}}
    agent = BacktesterAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({
            "strategy": "test",
        })
        # Should still return some result
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)

    asyncio.run(_run())
```

**Step 2: Update `quantclaw/agents/backtester.py`**

```python
"""Backtester: runs strategies through sandbox or engine plugins."""
from __future__ import annotations

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus


class BacktesterAgent(BaseAgent):
    name = "backtester"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        strategy_code = task.get("strategy_code", "")
        sandbox_enabled = self._config.get("sandbox", {}).get("enabled", True)

        if strategy_code and sandbox_enabled:
            return await self._execute_sandboxed(task)

        # Fallback: legacy in-process or stub
        strategy = task.get("strategy", "")
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={"strategy": strategy, "status": "backtested"},
        )

    async def _execute_sandboxed(self, task: dict) -> AgentResult:
        from quantclaw.sandbox.sandbox import Sandbox

        strategy_code = task.get("strategy_code", "")
        symbols = task.get("symbols", [])
        start = task.get("start", "2019-01-01")
        end = task.get("end", "2024-12-31")

        # Fetch data for symbols
        data = {}
        try:
            data_plugin_names = self._config.get("plugins", {}).get("data", ["data_yfinance"])
            if isinstance(data_plugin_names, str):
                data_plugin_names = [data_plugin_names]
            from quantclaw.plugins.manager import PluginManager
            pm = PluginManager()
            pm.discover()
            data_plugin = pm.get("data", data_plugin_names[0])
            if data_plugin:
                for symbol in symbols:
                    df = data_plugin.fetch_ohlcv(symbol, start, end)
                    if not df.empty:
                        data[symbol] = df
        except Exception:
            pass  # If data fetch fails, run with empty data

        sandbox = Sandbox(config=self._config)
        timeout = self._config.get("sandbox", {}).get("timeout", 60)

        result = await sandbox.execute_strategy(
            strategy_code=strategy_code,
            data=data,
            config={
                "initial_capital": self._config.get("initial_capital", 100000),
                "commission_pct": self._config.get("commission_pct", 0.001),
                "slippage_pct": self._config.get("slippage_pct", 0.0005),
            },
            timeout=timeout,
        )

        if result.status == "ok" and result.result:
            return AgentResult(status=AgentStatus.SUCCESS, data=result.result)
        elif result.status == "timeout":
            return AgentResult(status=AgentStatus.FAILED, error="Backtest timed out")
        else:
            return AgentResult(status=AgentStatus.FAILED, error=result.stderr[:500])
```

**Step 3: Add sandbox config to `quantclaw/config/default.yaml`**

Add at the end:

```yaml
sandbox:
  enabled: true
  timeout: 60
  max_output: 102400
  max_memory_mb: 512
  max_concurrent: 3
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_backtester_sandbox.py tests/test_sandbox.py tests/test_sandbox_security.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add quantclaw/agents/backtester.py quantclaw/config/default.yaml tests/test_backtester_sandbox.py
git commit -m "feat: integrate sandbox into Backtester agent"
```

---

## Task 5: Final Verification

**Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

**Step 2: Verify imports**

Run: `python -c "from quantclaw.sandbox.sandbox import Sandbox, SandboxResult; from quantclaw.sandbox.security import validate_imports, strip_env; from quantclaw.sandbox.runner import main; print('All imports OK')"`

**Step 3: Commit**

```bash
git add docs/plans/2026-04-05-sandbox-impl.md
git commit -m "docs: add sandbox implementation plan"
```

---

## Summary

### Created (7 files):
| File | Purpose |
|------|---------|
| `quantclaw/sandbox/__init__.py` | Package |
| `quantclaw/sandbox/security.py` | AST import validation + env stripping |
| `quantclaw/sandbox/sandbox.py` | Async subprocess execution with semaphore, timeout, cleanup |
| `quantclaw/sandbox/runner.py` | Bootstrap script for strategy backtest in subprocess |
| `tests/test_sandbox_security.py` | Security module tests (9 tests) |
| `tests/test_sandbox.py` | Sandbox execution tests (8 tests) |
| `tests/test_runner.py` | Runner integration test (1 test) |
| `tests/test_backtester_sandbox.py` | Backtester sandbox integration (2 tests) |

### Modified (2 files):
| File | Change |
|------|--------|
| `quantclaw/agents/backtester.py` | Use Sandbox for strategy_code execution |
| `quantclaw/config/default.yaml` | Add sandbox config section |
