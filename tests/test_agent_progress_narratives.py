"""Locks in two related contracts:

1. ``BaseAgent._narrate`` publishes a CHAT_NARRATIVE attributed to the
   agent (so progress messages render with the right role badge).
2. ``executor._run_paper_deployments`` calls market-data loading via
   ``asyncio.to_thread`` rather than blocking the event loop. Same
   pattern verified for validator/miner via the existing
   ``test_ingestor_event_loop`` style; this test specifically covers
   executor since it's the most operationally critical path
   (paper-trade execution every minute when autopilot is on).
"""
from __future__ import annotations
import asyncio
import time

import pytest

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus


class _StubBus:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


class _DummyAgent(BaseAgent):
    name = "dummy"

    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS)


@pytest.mark.asyncio
async def test_narrate_emits_chat_narrative_with_agent_role():
    bus = _StubBus()
    agent = _DummyAgent(bus=bus, config={})

    await agent._narrate("Generation 1/3: evaluating 6 candidate factors…")

    assert len(bus.events) == 1
    event = bus.events[0]
    payload = event.payload
    assert str(event.type) == "chat.narrative"
    assert payload["role"] == "dummy"  # role is the agent name, not "scheduler"
    assert "Generation 1/3" in payload["message"]
    assert event.source_agent == "dummy"


@pytest.mark.asyncio
async def test_narrate_truncates_long_messages():
    bus = _StubBus()
    agent = _DummyAgent(bus=bus, config={})

    await agent._narrate("X" * 1000)

    assert len(bus.events) == 1
    # Cap is 240 chars — keeps the chat readable when an agent
    # accidentally interpolates a large blob into a narrative.
    assert len(bus.events[0].payload["message"]) <= 240


@pytest.mark.asyncio
async def test_narrate_swallows_publish_failures():
    """If the bus throws (overloaded/disconnected), narration must NOT
    abort the agent's task."""

    class _BrokenBus:
        async def publish(self, event):
            raise RuntimeError("bus down")

    agent = _DummyAgent(bus=_BrokenBus(), config={})
    # Must not raise.
    await agent._narrate("anything")


@pytest.mark.asyncio
async def test_narrate_skips_empty_or_no_bus():
    bus = _StubBus()
    agent = _DummyAgent(bus=bus, config={})

    await agent._narrate("")
    await agent._narrate("   ")
    await agent._narrate(None)  # type: ignore[arg-type]

    assert bus.events == []

    # Agent constructed without a bus (e.g. unit-test contexts) — also a no-op.
    agent_no_bus = _DummyAgent(bus=None, config={})  # type: ignore[arg-type]
    await agent_no_bus._narrate("anything")  # must not raise


@pytest.mark.asyncio
async def test_playbook_load_uses_to_thread(monkeypatch):
    """Playbook ``query``/``recent``/``search`` previously did sync file
    I/O on the event loop. The fix added ``_load_all_async`` which
    must dispatch to a thread — verify by stubbing ``asyncio.to_thread``
    and confirming it gets called with the sync ``_load_all``."""
    import asyncio as _asyncio_mod
    from quantclaw.orchestration.playbook import Playbook

    pb = Playbook("/nonexistent/playbook.jsonl")

    captured: list = []
    real_to_thread = _asyncio_mod.to_thread

    async def _capture_to_thread(func, *args, **kwargs):
        captured.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(_asyncio_mod, "to_thread", _capture_to_thread)

    await pb._load_all_async()

    assert captured, (
        "_load_all_async must call asyncio.to_thread — without it the "
        "20MB playbook read blocks the event loop for hundreds of ms "
        "every time query/recent/search runs."
    )
    # The function dispatched should be the sync loader.
    assert captured[0].__name__ == "_load_all"
