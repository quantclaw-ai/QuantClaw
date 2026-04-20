"""Tests for LLMRouter cost tracking and budget warning emission."""
import asyncio

import pytest

from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.execution.router import CostTracker, LLMRouter, _lookup_rate


def test_router_rejects_cross_provider_oauth(monkeypatch):
    """Router must NOT forward provider-X's OAuth token to provider-Y.

    Reproduces the "Invalid bearer token" 401 that happened when a user
    signed into OpenAI OAuth but an agent resolved to Anthropic: the router
    was sending the OpenAI bearer to the Anthropic sidecar endpoint.
    After the fix the router refuses to call the sidecar without a token
    valid for the requested provider and surfaces a friendly error.
    """
    # Pretend the oauth store has ONLY an openai token.
    import quantclaw.dashboard.oauth as oauth_mod
    monkeypatch.setattr(oauth_mod, "_load_credentials", lambda: {
        "openai": {"access_token": "oa-token", "refresh_token": "rt", "expires_at": 2**31 - 1},
    })
    monkeypatch.setattr(oauth_mod, "get_access_token", lambda p: "oa-token" if p == "openai" else None)

    router = LLMRouter(config={
        "models": {"planner": "opus"},  # resolves to anthropic
        "providers": {"opus": {"provider": "anthropic", "model": "claude-opus-4-6"}},
        "oauth_token": "oa-token",  # legacy field — router must still not send this to anthropic
    })

    sidecar_calls: list[tuple[str, str]] = []

    async def _fail_if_called(self, provider, model, messages, system, temperature, access_token=None):
        sidecar_calls.append((provider, access_token or ""))
        return "SHOULD NOT HAPPEN"

    router._call_sidecar = _fail_if_called.__get__(router, LLMRouter)

    async def _run():
        with pytest.raises(RuntimeError) as exc:
            await router.call("planner", messages=[{"role": "user", "content": "plan"}])
        return exc.value

    err = asyncio.run(_run())
    # The router must NOT have called the anthropic sidecar with the openai token.
    for provider, tok in sidecar_calls:
        assert not (provider == "anthropic" and tok == "oa-token"), (
            "Router sent OpenAI OAuth token to Anthropic sidecar — the exact bug we fixed."
        )
    # Error should be the friendly one, mentioning anthropic.
    assert "anthropic" in str(err).lower() or "claude" in str(err).lower()


def test_router_uses_matching_provider_oauth(monkeypatch):
    """When a token exists for the right provider, the router uses it."""
    import quantclaw.dashboard.oauth as oauth_mod
    monkeypatch.setattr(oauth_mod, "_load_credentials", lambda: {
        "anthropic": {"access_token": "a-token", "refresh_token": "rt", "expires_at": 2**31 - 1},
    })
    monkeypatch.setattr(oauth_mod, "get_access_token", lambda p: "a-token" if p == "anthropic" else None)

    router = LLMRouter(config={
        "models": {"planner": "opus"},
        "providers": {"opus": {"provider": "anthropic", "model": "claude-opus-4-6"}},
    })

    captured: list[str] = []

    async def _fake_sidecar(self, provider, model, messages, system, temperature, access_token=None):
        captured.append(access_token or "")
        return "ok"

    router._call_sidecar = _fake_sidecar.__get__(router, LLMRouter)

    async def _run():
        return await router.call("planner", messages=[{"role": "user", "content": "plan"}])

    result = asyncio.run(_run())
    assert result == "ok"
    assert captured == ["a-token"]


def test_lookup_rate_longest_match():
    rates = {"gpt-4o": (2.5, 10.0), "gpt-4o-mini": (0.15, 0.60)}
    assert _lookup_rate("gpt-4o-mini", rates) == (0.15, 0.60)
    assert _lookup_rate("gpt-4o", rates) == (2.5, 10.0)


def test_lookup_rate_unknown_model_returns_zero():
    assert _lookup_rate("some-unknown-model", {}) == (0.0, 0.0)


def test_cost_tracker_accumulates():
    tracker = CostTracker(budget_usd=1.0, rates={"gpt-4o": (2.5, 10.0)})
    cost = tracker.record("miner", "gpt-4o", input_tokens=1000, output_tokens=500)
    assert cost == pytest.approx((1000 * 2.5 + 500 * 10.0) / 1_000_000)
    assert tracker.total_usd == pytest.approx(cost)
    assert tracker.per_agent_usd["miner"] == pytest.approx(cost)
    assert tracker.per_model_tokens["gpt-4o"] == {"input": 1000, "output": 500}


def test_cost_tracker_threshold_fires_once_per_level():
    # rate = $1.00 per 1M input tokens, so 400K tokens = $0.40
    tracker = CostTracker(budget_usd=1.0, rates={"m": (1.0, 0.0)})
    # Spend $0.40 — under all thresholds
    tracker.record("a", "m", 400_000, 0)
    assert tracker.next_threshold_to_fire() is None
    # Spend $0.20 more → total $0.60, crosses 0.5
    tracker.record("a", "m", 200_000, 0)
    assert tracker.next_threshold_to_fire() == 0.5
    # Same threshold doesn't re-fire
    assert tracker.next_threshold_to_fire() is None
    # Spend to $0.85 → crosses 0.8
    tracker.record("a", "m", 250_000, 0)
    assert tracker.next_threshold_to_fire() == 0.8


def test_cost_tracker_unknown_model_yields_zero_cost():
    tracker = CostTracker(budget_usd=1.0, rates={})
    cost = tracker.record("miner", "mystery-model-7b", 100_000, 50_000)
    assert cost == 0.0
    assert tracker.total_usd == 0.0


class _StubResponse:
    def __init__(self, text, in_tok, out_tok):
        self.content = [type("Block", (), {"text": text})()]
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": text})()})()]
        self.usage = type("U", (), {
            "input_tokens": in_tok, "output_tokens": out_tok,
            "prompt_tokens": in_tok, "completion_tokens": out_tok,
        })()


def test_budget_warning_event_fires(monkeypatch):
    """End-to-end: router records cost and publishes event once budget crossed."""
    # Force the API-key path by hiding any real oauth creds on disk.
    import quantclaw.dashboard.oauth as oauth_mod
    monkeypatch.setattr(oauth_mod, "get_access_token", lambda _p: None)
    monkeypatch.setattr(oauth_mod, "_load_credentials", lambda: {})

    bus = EventBus()
    received: list = []

    async def _capture(event):
        received.append(event)

    bus.subscribe(EventType.COST_BUDGET_WARNING, _capture)

    router = LLMRouter(
        config={
            "models": {"miner": "gpt"},
            "providers": {"gpt": {"provider": "openai", "model": "gpt-4o"}},
            "api_key": "sk-test",
            "cost": {
                "budget_usd": 0.01,  # tiny budget so we trip immediately
                "warning_thresholds": [0.5],
                "rates": {"gpt-4o": [5.0, 15.0]},
            },
        },
        event_bus=bus,
    )

    async def _fake_openai(self, model, messages, system, temperature):
        return "hi", 1000, 1000  # $0.02 cost on our tiny rates

    router._call_openai = _fake_openai.__get__(router, LLMRouter)

    async def _run():
        await router.call("miner", messages=[{"role": "user", "content": "x"}])
        # Give the event bus a moment to dispatch
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert router.cost.total_usd > 0
    assert len(received) == 1
    assert received[0].type == EventType.COST_BUDGET_WARNING
    assert received[0].payload["threshold_pct"] == 50


def test_router_works_without_event_bus(monkeypatch):
    """Cost tracking should still accumulate even if no event_bus is attached."""
    import quantclaw.dashboard.oauth as oauth_mod
    monkeypatch.setattr(oauth_mod, "get_access_token", lambda _p: None)
    monkeypatch.setattr(oauth_mod, "_load_credentials", lambda: {})

    router = LLMRouter(
        config={
            "models": {"m": "gpt"},
            "providers": {"gpt": {"provider": "openai", "model": "gpt-4o"}},
            "api_key": "sk-test",
            "cost": {"budget_usd": 0.01, "warning_thresholds": [0.5],
                     "rates": {"gpt-4o": [5.0, 15.0]}},
        },
        event_bus=None,
    )

    async def _fake_openai(self, model, messages, system, temperature):
        return "hi", 100, 100

    router._call_openai = _fake_openai.__get__(router, LLMRouter)

    async def _run():
        await router.call("m", messages=[{"role": "user", "content": "x"}])

    asyncio.run(_run())
    assert router.cost.total_usd > 0
