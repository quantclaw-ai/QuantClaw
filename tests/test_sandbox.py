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
        code = 'import json\nRESULT = {"answer": 42}\nprint(json.dumps(RESULT))'
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
        code = "import time; time.sleep(0.5); print('done')"
        results = await asyncio.gather(
            sandbox.execute_code(code),
            sandbox.execute_code(code),
        )
        assert all(r.status == "ok" for r in results)

    asyncio.run(_run())


def test_execute_code_with_data():
    import pandas as pd
    import numpy as np

    sandbox = Sandbox(config={})
    dates = pd.date_range("2023-01-01", periods=20, freq="B")
    data = {
        "AAPL": pd.DataFrame({
            "close": np.random.uniform(150, 160, 20),
        }, index=dates),
    }

    async def _run():
        code = '''
import pandas as pd
import json
from pathlib import Path

files = list(Path("data").glob("*.parquet"))
symbols = [f.stem for f in files]
data = {f.stem: pd.read_parquet(f) for f in files}
rows = {s: len(df) for s, df in data.items()}
print(json.dumps({"symbols": symbols, "rows": rows}))
'''
        result = await sandbox.execute_code(code, data=data)
        assert result.status == "ok"
        assert "AAPL" in result.result["symbols"]
        assert result.result["rows"]["AAPL"] == 20

    asyncio.run(_run())


def test_env_stripped():
    sandbox = Sandbox(config={})

    async def _run():
        code = 'import os, json\nenv = dict(os.environ)\nhas_key = any("KEY" in k for k in env)\nprint(json.dumps({"has_secret_key": has_key}))'
        result = await sandbox.execute_code(code)
        assert result.status == "ok"
        assert result.result["has_secret_key"] is False

    asyncio.run(_run())
