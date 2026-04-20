"""Tests for shared web search tool."""
import pytest
from quantclaw.agents.tools.web_search import get_search_provider, is_search_allowed


def test_get_default_provider():
    config = {}
    provider = get_search_provider(config)
    assert provider == "duckduckgo"


def test_get_configured_provider():
    config = {"search": {"provider": "brave"}}
    provider = get_search_provider(config)
    assert provider == "brave"


def test_search_policy_allowed():
    assert is_search_allowed("researcher")
    assert is_search_allowed("miner")
    assert is_search_allowed("scheduler")
    assert is_search_allowed("ingestor")
    assert is_search_allowed("trainer")


def test_search_policy_denied():
    assert not is_search_allowed("executor")
    assert not is_search_allowed("compliance")
