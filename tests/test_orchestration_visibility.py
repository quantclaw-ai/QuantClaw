"""Tests for the four-fix bundle that unsticks the chat after 'go make money'.

Fix B: Researcher accepts the planner's actual output shape (goal/task), not
       just the prompt-template-perfect topic/query fields.
Fix D: OODA cycle emits CHAT_NARRATIVE at every phase boundary so the chat
       doesn't go silent during decide() / act() (10-30s LLM + agent dispatch).
"""
from __future__ import annotations
import asyncio

import pytest

from quantclaw.agents.base import AgentStatus
from quantclaw.agents.researcher import ResearcherAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType


class _StubBus:
    """Captures published events without going through real subscribers."""

    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


# ── Fix B: Researcher contract robustness ──

@pytest.fixture
def researcher():
    return ResearcherAgent(config={}, bus=EventBus())


def test_researcher_accepts_goal_when_topic_missing(researcher, monkeypatch):
    """Planner emits {task: 'search_approaches', goal: '...'} without
    topic/query — the live failure mode from data/logs/backend.log.
    Researcher must fall back to ``goal`` instead of returning FAILED."""
    received_topic = {}

    async def _fake_research(topic, task_type, context):
        received_topic["topic"] = topic
        received_topic["task_type"] = task_type
        return {"summary": "ok"}

    monkeypatch.setattr(researcher, "_research_with_tools", _fake_research)

    result = asyncio.run(researcher.execute({
        "task": "search_approaches",
        "goal": "Campaign objective: go make money. Find profitable signals.",
    }))

    assert result.status == AgentStatus.SUCCESS
    assert received_topic["topic"] == "Campaign objective: go make money. Find profitable signals."
    assert received_topic["task_type"] == "search_approaches"


def test_researcher_falls_back_to_task_name_as_topic(researcher, monkeypatch):
    """If only ``task`` is set (and not 'search'), use it as the topic.
    Means a step like {task: 'find_factors'} is not silently dropped."""
    received_topic = {}

    async def _fake_research(topic, task_type, context):
        received_topic["topic"] = topic
        return {"summary": "ok"}

    monkeypatch.setattr(researcher, "_research_with_tools", _fake_research)

    result = asyncio.run(researcher.execute({"task": "find_alpha_factors"}))
    assert result.status == AgentStatus.SUCCESS
    assert received_topic["topic"] == "find_alpha_factors"


def test_researcher_still_prefers_explicit_topic(researcher, monkeypatch):
    """When topic IS provided, it wins over goal — so we don't accidentally
    regress on the existing happy path."""
    received_topic = {}

    async def _fake_research(topic, task_type, context):
        received_topic["topic"] = topic
        return {"summary": "ok"}

    monkeypatch.setattr(researcher, "_research_with_tools", _fake_research)

    result = asyncio.run(researcher.execute({
        "topic": "momentum factors",
        "goal": "make money",  # should be ignored
        "task": "search_factors",
    }))
    assert result.status == AgentStatus.SUCCESS
    assert received_topic["topic"] == "momentum factors"


def test_researcher_still_fails_when_truly_empty(researcher):
    """The empty-input failure path is still reachable — we widened the
    inputs, didn't make researcher accept absolutely anything."""
    result = asyncio.run(researcher.execute({"task": "search"}))
    assert result.status == AgentStatus.FAILED
    assert "topic" in (result.error or "").lower()


# ── Fix D: Phase narratives ──

def test_narrate_phase_emits_chat_narrative_event():
    """Every phase boundary in run_cycle calls _narrate_phase. The
    helper must publish a CHAT_NARRATIVE on the bus so the dashboard
    sees progress between Plan and Act (which can be 10-30s of silence
    with LLM + agent dispatch)."""
    from quantclaw.orchestration.ooda import OODALoop

    # Build a minimal OODA-shaped object that exposes _bus and the
    # _narrate_phase method without booting the full pipeline.
    class _MinimalOODA:
        _bus = _StubBus()
        _narrate_phase = OODALoop._narrate_phase

    instance = _MinimalOODA()
    asyncio.run(instance._narrate_phase("Planning the next steps…"))

    assert len(instance._bus.events) == 1
    event = instance._bus.events[0]
    assert event.type == EventType.CHAT_NARRATIVE
    assert event.payload["message"] == "Planning the next steps…"
    assert event.payload["role"] == "scheduler"
    assert event.source_agent == "scheduler"


def test_narrate_phase_swallows_publish_failures():
    """A bus failure during narration must NOT abort the cycle. This is
    why _narrate_phase wraps publish in try/except."""
    from quantclaw.orchestration.ooda import OODALoop

    class _BrokenBus:
        async def publish(self, event):
            raise RuntimeError("bus exploded")

    class _MinimalOODA:
        _bus = _BrokenBus()
        _narrate_phase = OODALoop._narrate_phase

    instance = _MinimalOODA()
    # Must not raise.
    asyncio.run(instance._narrate_phase("anything"))
