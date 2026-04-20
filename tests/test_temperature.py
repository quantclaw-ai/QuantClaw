"""Tests for per-agent temperature routing."""
from quantclaw.execution.router import LLMRouter

DEFAULT_TEMPS = {
    "miner": 0.9,
    "researcher": 0.7,
    "scheduler": 0.5,
    "trainer": 0.5,
    "debugger": 0.3,
    "reporter": 0.3,
    "ingestor": 0.2,
    "validator": 0.2,
    "sentinel": 0.2,
    "risk_monitor": 0.1,
    "executor": 0.1,
    "compliance": 0.1,
}


def test_default_temperatures():
    config = {"models": {}, "providers": {}}
    router = LLMRouter(config)
    for agent, expected_temp in DEFAULT_TEMPS.items():
        assert router.get_temperature(agent) == expected_temp, f"{agent} temp mismatch"


def test_config_overrides_temperature():
    config = {"models": {}, "providers": {}, "temperatures": {"miner": 0.5}}
    router = LLMRouter(config)
    assert router.get_temperature("miner") == 0.5


def test_unknown_agent_gets_default():
    config = {"models": {}, "providers": {}}
    router = LLMRouter(config)
    assert router.get_temperature("unknown_agent") == 0.5
