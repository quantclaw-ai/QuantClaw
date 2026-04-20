# Agent Sandbox — Design Document

**Date:** 2026-04-05
**Status:** Approved (v2 — audit fixes)
**Author:** Harry + Claude
**Inspired by:** DeerFlow 2.0 LocalSandboxProvider

## Problem

The Miner, Backtester, and Trainer agents execute LLM-generated Python code directly in the main process via `importlib`. This code has full access to the host — filesystem, network, environment variables. One bad generation could delete files, leak API keys, or crash the server.

## Solution

Subprocess sandbox with guardrails. Zero setup — uses Python's `asyncio.create_subprocess_exec()` with restrictions. No Docker, no cloud API, no extra install.

**Important: This is NOT a security boundary.** A determined adversary can escape subprocess restrictions. The guardrails prevent accidental damage from LLM-generated code (the 99% case). For real isolation → Docker mode (future upgrade).

## How It Works

```
Agent has code to execute
  → AST scan for dangerous imports (defense-in-depth, bypassable but catches most LLM output)
  → Write code + data files to isolated temp directory
  → asyncio.create_subprocess_exec("python", temp_file, ...)
    - cwd = temp directory (organizes temp files, NOT a filesystem jail)
    - timeout = 60 seconds (kills process tree on exceed)
    - env = stripped (no API keys, no secrets — actual values removed)
    - stdout/stderr captured (max 100KB)
    - memory limit via resource.setrlimit (Linux/Mac)
    - concurrency limited by semaphore (max 3 concurrent)
  → Parse results from stdout (JSON)
  → Cleanup temp directory
  → Return results to agent
```

## Sandbox Interface

```python
class Sandbox:
    def __init__(self, config: dict, max_concurrent: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_code(self, code: str, timeout: int = 60) -> SandboxResult:
        """Execute Python code in an isolated subprocess."""

    async def execute_strategy(self, strategy_path: str, data_dir: str, config: dict) -> SandboxResult:
        """Run a strategy backtest in an isolated subprocess.
        data_dir contains parquet files for each symbol."""
```

`SandboxResult`: `{status: ok|error|timeout, stdout: str, stderr: str, result: dict | None}`

## Guardrails

| Guardrail | How | Limitation |
|---|---|---|
| **Timeout** | `asyncio.wait_for` + `process.kill()` — kills on exceed | Windows may not kill child processes cleanly |
| **Working directory** | `tempfile.mkdtemp()` — organizes temp files | NOT a filesystem jail — process can access any path |
| **Environment** | Stripped env — only `PATH`, `PYTHONPATH`, `HOME`. All `*KEY*`, `*TOKEN*`, `*SECRET*` vars removed | Process can still read files on disk |
| **AST validation** | Pre-scan for dangerous imports (`os.system`, `subprocess`, `shutil.rmtree`, `socket`) | Bypassable via `exec()`, `__import__()`, `getattr` tricks. Defense-in-depth only |
| **Output size** | Capture max 100KB stdout, truncate if larger | — |
| **Memory limit** | `resource.setrlimit(RLIMIT_AS, max_memory)` in subprocess preexec | Linux/Mac only. No enforcement on Windows |
| **Concurrency** | `asyncio.Semaphore(3)` — max 3 concurrent sandbox processes | — |
| **Cleanup** | `shutil.rmtree(temp_dir)` in a `finally` block — always cleans up | — |
| **Async execution** | `asyncio.create_subprocess_exec` — does NOT block the event loop | — |

### Allowed imports (whitelist for AST check)

```python
ALLOWED_IMPORTS = {
    "math", "statistics", "datetime", "json", "re", "collections",
    "itertools", "functools", "decimal", "fractions",
    "numpy", "pandas", "scipy", "sklearn", "statsmodels",
}
```

Anything not in the whitelist triggers a warning in the result (not a hard block — the Scheduler can decide whether to proceed).

## Data Serialization

Backtests require pandas DataFrames (OHLCV data). DataFrames can't be JSON-serialized. Solution: serialize to parquet files in the temp directory.

```
Sandbox.execute_strategy():
  1. Create temp directory
  2. For each symbol in data: df.to_parquet(temp_dir / f"{symbol}.parquet")
  3. Write config to temp_dir / "config.json"
  4. Write strategy file to temp_dir / "strategy.py"
  5. Run runner.py in subprocess with temp_dir as argument
  6. Runner loads parquet files, runs backtest, prints JSON result
```

The runner script (`runner.py`) handles deserialization:
```python
# Inside subprocess
for parquet_file in Path(data_dir).glob("*.parquet"):
    symbol = parquet_file.stem
    data[symbol] = pd.read_parquet(parquet_file)
```

## Which Agents Use It

| Agent | Uses Sandbox | What It Executes |
|---|---|---|
| **Backtester** | Yes | Strategy code via StrategyRunner |
| **Miner** | Yes | LLM-generated factor code |
| **Trainer** | Yes | ML training pipelines |
| All others | No | LLM calls only, no code execution |

Note: Miner and Trainer are currently stubs. This task implements the sandbox infrastructure. Their agent logic (evolutionary mining loop, ML pipeline) is a separate task — but they'll use `Sandbox.execute_code()` when implemented.

## Integration with Existing Code

The `StrategyRunner.backtest()` currently runs in-process. The sandbox wraps this:

```
Before:  BacktesterAgent → StrategyRunner.backtest() → engine.backtest(strategy, data) [in-process]
After:   BacktesterAgent → Sandbox.execute_strategy(path, data_dir, config) → subprocess → runner.py → StrategyRunner [isolated]
```

The subprocess imports QuantClaw modules via PYTHONPATH. This means the subprocess CAN access QuantClaw internals (config loader, etc.), but the stripped environment removes actual secret values, so there's nothing sensitive to steal. For true module isolation → Docker mode.

## Subprocess Runner Script

A bootstrap script runs inside the subprocess:

```python
# quantclaw/sandbox/runner.py — executed in subprocess
# Usage: python runner.py <temp_dir>
# Reads: temp_dir/strategy.py, temp_dir/*.parquet, temp_dir/config.json
# Outputs: BacktestResult as JSON to stdout
# Exit code: 0 = success, 1 = error
```

For `execute_code` (Miner/Trainer), a simpler runner:
```python
# quantclaw/sandbox/code_runner.py
# Usage: python code_runner.py <temp_dir>/code.py
# Executes the code, captures result from a `RESULT` variable
# Outputs: JSON to stdout
```

## Memory Limits

On Linux/Mac, the subprocess sets memory limits via `resource.setrlimit`:

```python
import resource

def _set_memory_limit():
    max_bytes = max_memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))

# Used as preexec_fn in subprocess creation (Linux/Mac only)
```

On Windows, memory limiting is not enforced (no `resource` module). The timeout remains the primary guardrail.

Default: 512 MB per subprocess.

## Configuration

```yaml
sandbox:
  enabled: true
  timeout: 60          # seconds per execution
  max_output: 102400   # bytes (100KB)
  max_memory_mb: 512   # per subprocess (Linux/Mac only)
  max_concurrent: 3    # concurrent sandbox processes
  provider: subprocess  # default, zero-setup
  # provider: docker    # future, requires Docker
```

## Future: Docker Mode

When users want real isolation, add a `DockerSandboxProvider` that runs the same runner script inside a container. The interface stays identical — agents don't know or care which sandbox backend is used.

## What Changes

| File | Change |
|---|---|
| Create: `quantclaw/sandbox/__init__.py` | Package |
| Create: `quantclaw/sandbox/sandbox.py` | Sandbox class with execute_code, execute_strategy |
| Create: `quantclaw/sandbox/runner.py` | Bootstrap script for strategy backtest in subprocess |
| Create: `quantclaw/sandbox/code_runner.py` | Bootstrap script for arbitrary code in subprocess |
| Create: `quantclaw/sandbox/security.py` | AST import validation, env stripping, memory limits |
| Modify: `quantclaw/agents/backtester.py` | Use Sandbox instead of in-process StrategyRunner |
| Modify: `quantclaw/config/default.yaml` | Add sandbox config section |
| Create: `tests/test_sandbox.py` | Sandbox tests |
