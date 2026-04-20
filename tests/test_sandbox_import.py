"""Test that quantclaw modules can be imported inside sandbox subprocesses."""
import asyncio
import pytest
from quantclaw.sandbox.sandbox import Sandbox


def test_factor_evaluator_importable_in_sandbox():
    """Verify factor_evaluator can be imported inside a sandbox subprocess."""
    sandbox = Sandbox(config={})

    async def _run():
        code = '''
import json
try:
    from quantclaw.sandbox.factor_evaluator import evaluate_factor
    # Quick test with empty data
    result = evaluate_factor({}, {})
    print(json.dumps({"imported": True, "result": result}))
except ImportError as e:
    print(json.dumps({"imported": False, "error": str(e)}))
'''
        result = await sandbox.execute_code(code)
        assert result.status == "ok", f"Sandbox failed: {result.stderr}"
        assert result.result["imported"] is True
        assert result.result["result"]["ic"] == 0.0

    asyncio.run(_run())


def test_model_trainer_importable_in_sandbox():
    """Verify model_trainer can be imported inside a sandbox subprocess."""
    sandbox = Sandbox(config={})

    async def _run():
        code = '''
import json
try:
    from quantclaw.sandbox.model_trainer import generate_training_script
    print(json.dumps({"imported": True}))
except ImportError as e:
    print(json.dumps({"imported": False, "error": str(e)}))
'''
        result = await sandbox.execute_code(code)
        assert result.status == "ok", f"Sandbox failed: {result.stderr}"
        assert result.result["imported"] is True

    asyncio.run(_run())


def test_engine_builtin_importable_in_sandbox():
    """Verify the backtest engine can be imported (already used by runner.py)."""
    sandbox = Sandbox(config={})

    async def _run():
        code = '''
import json
try:
    from quantclaw.plugins.builtin.engine_builtin import BuiltinEnginePlugin
    print(json.dumps({"imported": True}))
except ImportError as e:
    print(json.dumps({"imported": False, "error": str(e)}))
'''
        result = await sandbox.execute_code(code)
        assert result.status == "ok", f"Sandbox failed: {result.stderr}"
        assert result.result["imported"] is True

    asyncio.run(_run())
