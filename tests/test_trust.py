"""Tests for the progressive trust system."""
import asyncio
import pytest

from quantclaw.orchestration.trust import TrustManager, TrustLevel, RiskGuardrails


def test_initial_trust_level():
    tm = TrustManager()
    assert tm.level == TrustLevel.OBSERVER


def test_trust_level_capabilities():
    tm = TrustManager()
    assert tm.can_research()
    assert not tm.can_paper_trade()
    assert not tm.can_live_trade()


def test_upgrade_to_paper_trader():
    tm = TrustManager()
    asyncio.run(tm.upgrade(TrustLevel.PAPER_TRADER))
    assert tm.level == TrustLevel.PAPER_TRADER
    assert tm.can_paper_trade()
    assert not tm.can_live_trade()


def test_cannot_skip_levels():
    tm = TrustManager()
    with pytest.raises(ValueError, match="Cannot skip"):
        asyncio.run(tm.upgrade(TrustLevel.TRUSTED))


def test_upgrade_emits_event():
    """Trust upgrade emits trust.level_changed event."""
    from quantclaw.events.bus import EventBus
    bus = EventBus()
    captured = []
    async def capture(event):
        captured.append(event)
    bus.subscribe("trust.*", capture)

    tm = TrustManager(bus=bus)
    async def _run():
        await tm.upgrade(TrustLevel.PAPER_TRADER)
        await asyncio.sleep(0.05)
    asyncio.run(_run())
    assert len(captured) == 1
    assert captured[0].payload["new_level"] == "PAPER_TRADER"


def test_trust_persists_to_playbook(tmp_path):
    """Trust level persists to playbook and restores on startup."""
    from quantclaw.orchestration.playbook import Playbook
    pb = Playbook(str(tmp_path / "playbook.jsonl"))

    async def _run():
        tm = TrustManager(playbook=pb)
        await tm.upgrade(TrustLevel.PAPER_TRADER)

        # Restore from playbook
        tm2 = await TrustManager.from_playbook(pb)
        assert tm2.level == TrustLevel.PAPER_TRADER

    asyncio.run(_run())


def test_risk_guardrails_check():
    guardrails = RiskGuardrails(
        max_drawdown=-0.10,
        max_position_pct=0.05,
        auto_liquidate_at=-0.15,
    )
    assert guardrails.check_position_size(0.03, 100000)
    assert not guardrails.check_position_size(0.06, 100000)
    assert guardrails.check_drawdown(-0.05)
    assert not guardrails.check_drawdown(-0.12)


def test_risk_guardrails_from_config():
    config = {"risk": {"max_drawdown": -0.10, "max_position_pct": 0.05, "auto_liquidate_at": -0.15}}
    guardrails = RiskGuardrails.from_config(config)
    assert guardrails.max_drawdown == -0.10


def test_requires_escalation():
    tm = TrustManager()
    asyncio.run(tm.upgrade(TrustLevel.PAPER_TRADER))
    # First live trade always requires escalation
    assert tm.requires_escalation("live_trade")
    # Research does not
    assert not tm.requires_escalation("research")


def test_trust_metrics_tracking():
    tm = TrustManager()
    asyncio.run(tm.upgrade(TrustLevel.PAPER_TRADER))
    tm.record_trade_result(profit=100)
    tm.record_trade_result(profit=-30)
    tm.record_trade_result(profit=50)
    metrics = tm.get_metrics()
    assert metrics["total_trades"] == 3
    assert metrics["win_rate"] == pytest.approx(2 / 3)
    assert metrics["total_pnl"] == 120
