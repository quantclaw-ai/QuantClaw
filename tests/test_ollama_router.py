"""Tests for Ollama provider in LLMRouter."""
from quantclaw.execution.router import LLMRouter


def test_ollama_provider_config():
    config = {
        "models": {"scheduler": "local"},
        "providers": {"local": {"provider": "ollama", "model": "llama3.1"}},
    }
    router = LLMRouter(config)
    provider = router.get_provider("scheduler")
    assert provider["provider"] == "ollama"
    assert provider["model"] == "llama3.1"


def test_ollama_url_default():
    config = {"models": {}, "providers": {}}
    router = LLMRouter(config)
    assert router.get_ollama_url() == "http://localhost:11434"


def test_ollama_url_from_config():
    config = {"models": {}, "providers": {}, "ollama_url": "http://custom:11434"}
    router = LLMRouter(config)
    assert router.get_ollama_url() == "http://custom:11434"
