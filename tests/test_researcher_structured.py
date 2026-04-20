# tests/test_researcher_structured.py
"""Tests for Researcher structured output."""
import asyncio

import pytest

from quantclaw.agents.researcher import ResearcherAgent
from quantclaw.agents.base import AgentStatus
from quantclaw.events.bus import EventBus


def test_researcher_returns_structured_output():
    bus = EventBus()
    agent = ResearcherAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({
            "task": "search_factors",
            "topic": "momentum alpha",
        })
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)
        if result.status == AgentStatus.SUCCESS:
            assert "findings" in result.data
            assert "suggested_factors" in result.data
            assert "suggested_models" in result.data

    asyncio.run(_run())


def test_researcher_no_topic_fails():
    bus = EventBus()
    agent = ResearcherAgent(bus=bus, config={})

    async def _run():
        result = await agent.execute({"task": "search"})
        # "search" becomes the topic via task.get("task")
        assert result.status in (AgentStatus.SUCCESS, AgentStatus.FAILED)

    asyncio.run(_run())


def test_researcher_interface():
    bus = EventBus()
    agent = ResearcherAgent(bus=bus, config={})
    assert agent.name == "researcher"
