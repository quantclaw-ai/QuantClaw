from quantclaw.execution.router import LLMRouter
from quantclaw.config.loader import load_config

def test_router_returns_correct_model():
    config = load_config()
    router = LLMRouter(config)
    assert router.get_model("planner") == "opus"
    assert router.get_model("sentinel") == "sonnet"
    assert router.get_model("miner") == "gpt"

def test_router_returns_provider_config():
    config = load_config()
    router = LLMRouter(config)
    prov = router.get_provider("planner")
    assert prov["provider"] == "anthropic"
    assert prov["model"] == "claude-opus-4-6"
