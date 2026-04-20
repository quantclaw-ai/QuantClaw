"""Tests for the LLM tool-use loop infrastructure."""
import asyncio
import json
import pytest

from quantclaw.execution.tool_loop import (
    execute_tool,
    tools_for_anthropic,
    tools_for_openai,
    tools_for_responses_api,
    SEARCH_TOOL,
    DATA_FIELDS_TOOL,
    ALL_TOOLS,
)


def test_tool_definitions_have_required_fields():
    """All tool defs have name, description, parameters."""
    for tool in ALL_TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert tool["parameters"]["type"] == "object"


def test_anthropic_format():
    """Anthropic format uses input_schema."""
    formatted = tools_for_anthropic([SEARCH_TOOL])
    assert len(formatted) == 1
    t = formatted[0]
    assert t["name"] == "web_search"
    assert "input_schema" in t
    assert "description" in t
    assert "parameters" not in t  # Anthropic uses input_schema, not parameters


def test_openai_format():
    """OpenAI Chat Completions wraps in {type: function, function: {...}}."""
    formatted = tools_for_openai([SEARCH_TOOL])
    assert len(formatted) == 1
    t = formatted[0]
    assert t["type"] == "function"
    assert t["function"]["name"] == "web_search"
    assert "parameters" in t["function"]


def test_responses_api_format():
    """OpenAI Responses API uses flat {type: function, name: ..., parameters: ...}."""
    formatted = tools_for_responses_api([SEARCH_TOOL])
    assert len(formatted) == 1
    t = formatted[0]
    assert t["type"] == "function"
    assert t["name"] == "web_search"
    assert "parameters" in t


def test_execute_tool_available_fields():
    """available_data_fields tool returns field catalog."""
    config = {"plugins": {"data": ["data_yfinance"]}}

    async def _run():
        result = await execute_tool("available_data_fields", {}, config)
        data = json.loads(result)
        assert "ohlcv" in data
        assert "fundamentals" in data
        assert "sentiment" in data
        return data

    data = asyncio.run(_run())
    assert "open" in data["ohlcv"]


def test_execute_tool_unknown():
    """Unknown tools return an error."""
    async def _run():
        result = await execute_tool("nonexistent", {}, {})
        data = json.loads(result)
        assert "error" in data

    asyncio.run(_run())


def test_execute_tool_search_empty_query():
    """Search with empty query returns error."""
    async def _run():
        result = await execute_tool("web_search", {}, {})
        data = json.loads(result)
        assert "error" in data

    asyncio.run(_run())


def test_researcher_falls_back_gracefully():
    """Researcher uses fallback when tool-use fails."""
    from quantclaw.agents.researcher import ResearcherAgent
    from quantclaw.agents.base import AgentStatus
    from quantclaw.events.bus import EventBus

    bus = EventBus()
    # Config with no valid LLM — will fail tool-use and fallback
    config = {"plugins": {"data": ["data_yfinance"]}}
    agent = ResearcherAgent(bus=bus, config=config)

    async def _run():
        result = await agent.execute({"topic": "test query"})
        # Should not crash — returns success or failed, never exception
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)

    asyncio.run(_run())
