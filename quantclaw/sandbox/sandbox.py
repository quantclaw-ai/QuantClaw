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

    async def execute_code(self, code: str, timeout: int | None = None,
                           data: dict | None = None) -> SandboxResult:
        """Execute Python code in an isolated subprocess."""
        timeout = timeout or self._default_timeout

        # AST validation (defense-in-depth)
        warnings = validate_imports(code)
        warning_msgs = [w.message for w in warnings]

        # Block execution if any critical violation is present (non-allowed
        # imports, blocked builtins, dunder attribute access).
        critical = [w for w in warnings if w.critical]
        if critical:
            return SandboxResult(
                status="error",
                stderr=f"Security violation: {critical[0].message}",
                import_warnings=warning_msgs,
            )

        # Create temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix="qc_sandbox_"))
        try:
            # Write data files if provided
            if data:
                import pandas as pd
                data_dir = temp_dir / "data"
                data_dir.mkdir()
                for symbol, df in data.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        df.to_parquet(data_dir / f"{symbol}.parquet")

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

        data: dict of {symbol: DataFrame} -- serialized to parquet in temp dir.
        """
        import pandas as pd

        timeout = timeout or self._default_timeout

        # AST validation (defense-in-depth) — same guard as execute_code.
        warnings = validate_imports(strategy_code)
        warning_msgs = [w.message for w in warnings]
        critical = [w for w in warnings if w.critical]
        if critical:
            return SandboxResult(
                status="error",
                stderr=f"Security violation: {critical[0].message}",
                import_warnings=warning_msgs,
            )

        temp_dir = Path(tempfile.mkdtemp(prefix="qc_backtest_"))

        try:
            # Write strategy code
            (temp_dir / "strategy.py").write_text(strategy_code, encoding="utf-8")

            # Copy model files referenced in strategy into sandbox temp dir
            self._copy_model_files(strategy_code, temp_dir)

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
                import_warnings=warning_msgs,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _copy_model_files(strategy_code: str, temp_dir: Path) -> None:
        """Extract model source paths from strategy code and copy into sandbox."""
        import re
        for match in re.finditer(r'_model_src_path\s*=\s*"([^"]+)"', strategy_code):
            src = Path(match.group(1))
            if src.exists():
                dest_dir = temp_dir / "models"
                dest_dir.mkdir(exist_ok=True)
                shutil.copy2(str(src), str(dest_dir / src.name))

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
