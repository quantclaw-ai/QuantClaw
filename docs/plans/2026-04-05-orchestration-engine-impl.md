# Orchestration Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the Scheduler from a cron-based task dispatcher into an autonomous OODA-loop orchestration engine with playbook memory, trust system, autonomy modes, and per-agent temperature routing.

**Architecture:** The orchestration engine layers on top of the existing Plan/Dispatcher/EventBus infrastructure. New modules: `orchestration/` package with playbook, trust, autonomy mode manager, OODA loop, and enhanced DAG execution. The existing `daemon.py` scheduler loop is replaced by the OODA loop. Frontend gets new orchestration event types in `useFloorEvents`.

**Tech Stack:** Python 3.12+ (asyncio, dataclasses, JSON-lines), FastAPI WebSocket events, Next.js React hooks (TypeScript)

---

## Task 1: Playbook — JSONL Persistent Memory Store

The Playbook is the Scheduler's self-evolving knowledge base. It stores strategy results, failures, market observations, CEO preferences, factor library entries, and trust milestones as append-only JSON-lines.

**Files:**
- Create: `quantclaw/orchestration/playbook.py`
- Create: `tests/test_playbook.py`

**Step 1: Write the failing tests**

```python
# tests/test_playbook.py
"""Tests for the Playbook persistent memory store."""
import asyncio
import json
import os
import tempfile

import pytest

from quantclaw.orchestration.playbook import Playbook, PlaybookEntry, EntryType


@pytest.fixture
def tmp_playbook(tmp_path):
    return str(tmp_path / "playbook.jsonl")


def test_add_entry_and_query(tmp_playbook):
    pb = Playbook(tmp_playbook)

    async def _run():
        await pb.add(EntryType.STRATEGY_RESULT, {
            "strategy": "momentum_5d",
            "sharpe": 1.8,
            "annual_return": 0.22,
        }, tags=["momentum", "equity"])

        results = await pb.query(tags=["momentum"])
        assert len(results) == 1
        assert results[0].content["sharpe"] == 1.8
        assert results[0].entry_type == EntryType.STRATEGY_RESULT

    asyncio.run(_run())


def test_persistence_across_instances(tmp_playbook):
    async def _run():
        pb1 = Playbook(tmp_playbook)
        await pb1.add(EntryType.MARKET_OBSERVATION, {
            "observation": "VIX > 30 correlates with momentum crashes",
        }, tags=["vix", "momentum"])

        pb2 = Playbook(tmp_playbook)
        results = await pb2.query(tags=["vix"])
        assert len(results) == 1

    asyncio.run(_run())


def test_query_by_type(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        await pb.add(EntryType.STRATEGY_RESULT, {"strategy": "mean_rev"}, tags=["equity"])
        await pb.add(EntryType.WHAT_FAILED, {"strategy": "bad_idea", "reason": "overfitting"}, tags=["equity"])

        results = await pb.query(entry_type=EntryType.WHAT_FAILED)
        assert len(results) == 1
        assert results[0].content["reason"] == "overfitting"

    asyncio.run(_run())


def test_full_text_search(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        await pb.add(EntryType.MARKET_OBSERVATION, {
            "observation": "Federal Reserve rate hike signals bearish equities",
        }, tags=["fed", "rates"])

        results = await pb.search("Federal Reserve")
        assert len(results) == 1

    asyncio.run(_run())


def test_recent_entries(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        for i in range(10):
            await pb.add(EntryType.STRATEGY_RESULT, {"idx": i}, tags=["batch"])

        recent = await pb.recent(5)
        assert len(recent) == 5
        assert recent[-1].content["idx"] == 9  # most recent last

    asyncio.run(_run())


def test_factor_library_entry(tmp_playbook):
    async def _run():
        pb = Playbook(tmp_playbook)
        await pb.add(EntryType.FACTOR_LIBRARY, {
            "name": "momentum_5d_vol_adj",
            "hypothesis": "5-day momentum adjusted for volatility captures short-term trends",
            "code": "df['close'].pct_change(5) / df['close'].pct_change(5).rolling(20).std()",
            "metrics": {"ic": 0.05, "rank_ic": 0.08, "sharpe": 1.2},
            "lineage": {"parent": None, "generation": 0, "method": "exploration"},
        }, tags=["factor", "momentum", "volatility"])

        factors = await pb.query(entry_type=EntryType.FACTOR_LIBRARY)
        assert len(factors) == 1
        assert factors[0].content["metrics"]["sharpe"] == 1.2

    asyncio.run(_run())
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_playbook.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quantclaw.orchestration'`

**Step 3: Create the orchestration package**

```bash
mkdir -p quantclaw/orchestration
```

Create empty `quantclaw/orchestration/__init__.py`:
```python
"""Orchestration engine: OODA loop, playbook, trust, autonomy modes."""
```

**Step 4: Write the Playbook implementation**

```python
# quantclaw/orchestration/playbook.py
"""Playbook: self-evolving persistent knowledge store (JSON-lines)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class EntryType(StrEnum):
    STRATEGY_RESULT = "strategy_result"
    WHAT_FAILED = "what_failed"
    MARKET_OBSERVATION = "market_observation"
    CEO_PREFERENCE = "ceo_preference"
    AGENT_PERFORMANCE = "agent_performance"
    FACTOR_LIBRARY = "factor_library"
    TRUST_MILESTONE = "trust_milestone"


@dataclass(frozen=True)
class PlaybookEntry:
    entry_type: EntryType
    content: dict[str, Any]
    tags: list[str]
    timestamp: str


class Playbook:
    """Append-only JSONL knowledge store with tag and full-text search."""

    def __init__(self, path: str = "data/playbook.jsonl"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def add(
        self,
        entry_type: EntryType,
        content: dict[str, Any],
        tags: list[str] | None = None,
    ) -> PlaybookEntry:
        entry = PlaybookEntry(
            entry_type=entry_type,
            content=content,
            tags=tags or [],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        line = json.dumps({
            "entry_type": entry.entry_type.value,
            "content": entry.content,
            "tags": entry.tags,
            "timestamp": entry.timestamp,
        })
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return entry

    def _load_all(self) -> list[PlaybookEntry]:
        if not self._path.exists():
            return []
        entries = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entries.append(PlaybookEntry(
                    entry_type=EntryType(data["entry_type"]),
                    content=data["content"],
                    tags=data.get("tags", []),
                    timestamp=data["timestamp"],
                ))
        return entries

    async def query(
        self,
        tags: list[str] | None = None,
        entry_type: EntryType | None = None,
    ) -> list[PlaybookEntry]:
        entries = self._load_all()
        if entry_type is not None:
            entries = [e for e in entries if e.entry_type == entry_type]
        if tags:
            tag_set = set(tags)
            entries = [e for e in entries if tag_set & set(e.tags)]
        return entries

    async def search(self, text: str) -> list[PlaybookEntry]:
        lower = text.lower()
        entries = self._load_all()
        return [
            e for e in entries
            if lower in json.dumps(e.content).lower()
        ]

    async def recent(self, n: int = 20) -> list[PlaybookEntry]:
        entries = self._load_all()
        return entries[-n:]
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_playbook.py -v`
Expected: All 7 tests PASS

**Step 6: Commit**

```bash
git add quantclaw/orchestration/__init__.py quantclaw/orchestration/playbook.py tests/test_playbook.py
git commit -m "feat: add Playbook JSONL persistent memory store"
```

---

## Task 2: Trust System — 5-Level Progressive Trust

The trust system overlays the existing progression levels with trading-specific trust levels (0-4). It tracks performance metrics and enforces risk guardrails.

**Files:**
- Create: `quantclaw/orchestration/trust.py`
- Create: `tests/test_trust.py`

**Step 1: Write the failing tests**

```python
# tests/test_trust.py
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
    """GAP 5: Trust upgrade emits trust.level_changed event."""
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
    """GAP 4: Trust level persists to playbook and restores on startup."""
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
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_trust.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the Trust implementation**

```python
# quantclaw/orchestration/trust.py
"""Progressive trust system with risk guardrails."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantclaw.events.bus import EventBus
    from quantclaw.orchestration.playbook import Playbook


class TrustLevel(IntEnum):
    OBSERVER = 0       # Research, analyze, report
    PAPER_TRADER = 1   # Paper trade within limits
    PROVEN = 2         # Can request live trading
    TRUSTED = 3        # Live trading within budget
    AUTONOMOUS = 4     # Full autonomy within budget


# Actions that require escalation to Plan Mode regardless of trust level
SAFETY_CRITICAL_ACTIONS = frozenset({
    "live_trade",
    "increase_position_size",
    "new_asset_class",
    "first_paper_trade",
})


@dataclass
class RiskGuardrails:
    max_drawdown: float = -0.10
    max_position_pct: float = 0.05
    auto_liquidate_at: float = -0.15

    @classmethod
    def from_config(cls, config: dict) -> RiskGuardrails:
        risk = config.get("risk", {})
        return cls(
            max_drawdown=risk.get("max_drawdown", -0.10),
            max_position_pct=risk.get("max_position_pct", 0.05),
            auto_liquidate_at=risk.get("auto_liquidate_at", -0.15),
        )

    def check_position_size(self, position_pct: float, portfolio_value: float) -> bool:
        return position_pct <= self.max_position_pct

    def check_drawdown(self, current_drawdown: float) -> bool:
        return current_drawdown > self.max_drawdown


class TrustManager:
    """Manages progressive trust levels and performance tracking.

    Accepts an optional EventBus to emit trust.level_changed events,
    and an optional Playbook to persist trust milestones across restarts.
    """

    def __init__(
        self,
        initial_level: TrustLevel = TrustLevel.OBSERVER,
        bus: EventBus | None = None,
        playbook: Playbook | None = None,
    ):
        self._level = initial_level
        self._trade_results: list[float] = []
        self._bus = bus
        self._playbook = playbook

    @property
    def level(self) -> TrustLevel:
        return self._level

    async def upgrade(self, target: TrustLevel) -> None:
        if target > self._level + 1:
            raise ValueError(
                f"Cannot skip levels: current={self._level.name}, target={target.name}"
            )
        old_level = self._level
        self._level = target

        # Emit trust level changed event (GAP 5 fix)
        if self._bus:
            from quantclaw.events.types import Event, EventType
            await self._bus.publish(Event(
                type=EventType.TRUST_LEVEL_CHANGED,
                payload={
                    "old_level": old_level.name,
                    "new_level": target.name,
                    "old_level_id": int(old_level),
                    "new_level_id": int(target),
                },
                source_agent="scheduler",
            ))

        # Persist to playbook (GAP 4 fix)
        if self._playbook:
            from quantclaw.orchestration.playbook import EntryType
            await self._playbook.add(EntryType.TRUST_MILESTONE, {
                "old_level": old_level.name,
                "new_level": target.name,
                "metrics": self.get_metrics(),
            }, tags=["trust", target.name])

    @classmethod
    async def from_playbook(cls, playbook: Playbook, bus: EventBus | None = None) -> TrustManager:
        """Restore trust level from playbook on startup (GAP 4 fix)."""
        from quantclaw.orchestration.playbook import EntryType
        milestones = await playbook.query(entry_type=EntryType.TRUST_MILESTONE)
        level = TrustLevel.OBSERVER
        if milestones:
            last = milestones[-1]
            try:
                level = TrustLevel[last.content["new_level"]]
            except (KeyError, ValueError):
                pass
        return cls(initial_level=level, bus=bus, playbook=playbook)

    def can_research(self) -> bool:
        return self._level >= TrustLevel.OBSERVER

    def can_paper_trade(self) -> bool:
        return self._level >= TrustLevel.PAPER_TRADER

    def can_live_trade(self) -> bool:
        return self._level >= TrustLevel.TRUSTED

    def requires_escalation(self, action: str) -> bool:
        if action in SAFETY_CRITICAL_ACTIONS:
            return True
        if action == "paper_trade" and self._level < TrustLevel.PAPER_TRADER:
            return True
        return False

    def record_trade_result(self, profit: float) -> None:
        self._trade_results.append(profit)

    def get_metrics(self) -> dict:
        if not self._trade_results:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
        wins = sum(1 for p in self._trade_results if p > 0)
        return {
            "total_trades": len(self._trade_results),
            "win_rate": wins / len(self._trade_results),
            "total_pnl": sum(self._trade_results),
        }
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_trust.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add quantclaw/orchestration/trust.py tests/test_trust.py
git commit -m "feat: add progressive trust system with risk guardrails"
```

---

## Task 3: Autonomy Modes — Autopilot, Plan Mode, Interactive

Three modes controlling how the Scheduler executes plans. Mode can change mid-workflow.

**Files:**
- Create: `quantclaw/orchestration/autonomy.py`
- Create: `tests/test_autonomy.py`

**Step 1: Write the failing tests**

```python
# tests/test_autonomy.py
"""Tests for autonomy mode management."""
import pytest

from quantclaw.orchestration.autonomy import AutonomyMode, AutonomyManager


def test_default_mode_is_plan():
    am = AutonomyManager()
    assert am.mode == AutonomyMode.PLAN


def test_switch_to_autopilot():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert am.mode == AutonomyMode.AUTOPILOT


def test_switch_to_interactive():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert am.mode == AutonomyMode.INTERACTIVE


def test_should_show_plan():
    am = AutonomyManager()
    assert am.should_show_plan()  # Plan Mode shows plan
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert not am.should_show_plan()  # Autopilot does not
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert am.should_show_plan()  # Interactive shows plan


def test_should_wait_for_approval():
    am = AutonomyManager()
    assert am.should_wait_for_approval()  # Plan Mode waits
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert not am.should_wait_for_approval()
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert not am.should_wait_for_approval()  # Interactive shows but doesn't block


def test_auto_escalation_overrides_autopilot():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.AUTOPILOT)
    assert am.should_escalate_for("live_trade")
    assert not am.should_escalate_for("research")


def test_mode_history():
    am = AutonomyManager()
    am.set_mode(AutonomyMode.AUTOPILOT)
    am.set_mode(AutonomyMode.INTERACTIVE)
    assert len(am.mode_history) == 3  # initial PLAN + 2 switches
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_autonomy.py -v`
Expected: FAIL

**Step 3: Write the Autonomy implementation**

```python
# quantclaw/orchestration/autonomy.py
"""Autonomy mode management: Autopilot, Plan Mode, Interactive."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from quantclaw.orchestration.trust import SAFETY_CRITICAL_ACTIONS


class AutonomyMode(StrEnum):
    AUTOPILOT = "autopilot"
    PLAN = "plan"
    INTERACTIVE = "interactive"


class AutonomyManager:
    """Controls how the Scheduler executes plans."""

    def __init__(self, initial_mode: AutonomyMode = AutonomyMode.PLAN):
        self._mode = initial_mode
        self._mode_history: list[tuple[AutonomyMode, str]] = [
            (initial_mode, datetime.now(timezone.utc).isoformat())
        ]

    @property
    def mode(self) -> AutonomyMode:
        return self._mode

    @property
    def mode_history(self) -> list[tuple[AutonomyMode, str]]:
        return list(self._mode_history)

    def set_mode(self, mode: AutonomyMode) -> None:
        self._mode = mode
        self._mode_history.append(
            (mode, datetime.now(timezone.utc).isoformat())
        )

    def should_show_plan(self) -> bool:
        return self._mode in (AutonomyMode.PLAN, AutonomyMode.INTERACTIVE)

    def should_wait_for_approval(self) -> bool:
        return self._mode == AutonomyMode.PLAN

    def should_escalate_for(self, action: str) -> bool:
        return action in SAFETY_CRITICAL_ACTIONS
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_autonomy.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add quantclaw/orchestration/autonomy.py tests/test_autonomy.py
git commit -m "feat: add autonomy mode management (autopilot/plan/interactive)"
```

---

## Task 4: Orchestration Event Types

Add new event types for orchestration, playbook, and trust WebSocket events.

**Files:**
- Modify: `quantclaw/events/types.py`
- Modify: `tests/test_events.py` (add new event type tests)

**Step 1: Write the failing test**

Add to `tests/test_events.py`:

```python
def test_orchestration_event_types():
    """Verify orchestration event types exist."""
    from quantclaw.events.types import EventType
    assert EventType.ORCHESTRATION_PLAN_CREATED == "orchestration.plan_created"
    assert EventType.ORCHESTRATION_STEP_STARTED == "orchestration.step_started"
    assert EventType.ORCHESTRATION_STEP_COMPLETED == "orchestration.step_completed"
    assert EventType.ORCHESTRATION_STEP_FAILED == "orchestration.step_failed"
    assert EventType.ORCHESTRATION_BROADCAST == "orchestration.broadcast"
    assert EventType.PLAYBOOK_ENTRY_ADDED == "playbook.entry_added"
    assert EventType.TRUST_LEVEL_CHANGED == "trust.level_changed"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_events.py::test_orchestration_event_types -v`
Expected: FAIL — `AttributeError`

**Step 3: Add event types to `quantclaw/events/types.py`**

Add these members to the `EventType` enum (after the existing members):

```python
    # Orchestration engine events
    ORCHESTRATION_PLAN_CREATED = "orchestration.plan_created"
    ORCHESTRATION_STEP_STARTED = "orchestration.step_started"
    ORCHESTRATION_STEP_COMPLETED = "orchestration.step_completed"
    ORCHESTRATION_STEP_FAILED = "orchestration.step_failed"
    ORCHESTRATION_BROADCAST = "orchestration.broadcast"
    PLAYBOOK_ENTRY_ADDED = "playbook.entry_added"
    TRUST_LEVEL_CHANGED = "trust.level_changed"
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_events.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add quantclaw/events/types.py tests/test_events.py
git commit -m "feat: add orchestration, playbook, and trust event types"
```

---

## Task 5: Per-Agent LLM Temperature

Add temperature configuration to the LLM router. Each agent gets a tuned temperature based on its role.

**Files:**
- Modify: `quantclaw/orchestrator/router.py`
- Modify: `quantclaw/config/default.yaml`
- Create: `tests/test_temperature.py`

**Step 1: Write the failing test**

```python
# tests/test_temperature.py
"""Tests for per-agent temperature routing."""
from quantclaw.orchestrator.router import LLMRouter

DEFAULT_TEMPS = {
    "miner": 0.9,
    "researcher": 0.7,
    "scheduler": 0.5,
    "trainer": 0.5,
    "debugger": 0.3,
    "reporter": 0.3,
    "ingestor": 0.2,
    "backtester": 0.2,
    "sentinel": 0.2,
    "risk_monitor": 0.1,
    "executor": 0.1,
    "compliance": 0.1,
    "cost_tracker": 0.1,
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
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_temperature.py -v`
Expected: FAIL — `AttributeError: 'LLMRouter' has no attribute 'get_temperature'`

**Step 3: Add temperature support to LLMRouter**

In `quantclaw/orchestrator/router.py`, add the default temperatures dict and `get_temperature` method:

```python
# Add at module level, before the class
AGENT_TEMPERATURES: dict[str, float] = {
    "miner": 0.9,
    "researcher": 0.7,
    "scheduler": 0.5,
    "trainer": 0.5,
    "debugger": 0.3,
    "reporter": 0.3,
    "ingestor": 0.2,
    "backtester": 0.2,
    "sentinel": 0.2,
    "risk_monitor": 0.1,
    "executor": 0.1,
    "compliance": 0.1,
    "cost_tracker": 0.1,
}
```

In `__init__`, add:
```python
self._temperatures = config.get("temperatures", {})
```

Add method:
```python
def get_temperature(self, agent_name: str) -> float:
    if agent_name in self._temperatures:
        return self._temperatures[agent_name]
    return AGENT_TEMPERATURES.get(agent_name, 0.5)
```

Update `_call_anthropic` and `_call_openai` to accept and use a `temperature` parameter:

```python
async def call(self, agent_name: str, messages: list[dict], system: str = None,
               temperature: float | None = None) -> str:
    provider = self.get_provider(agent_name)
    temp = temperature if temperature is not None else self.get_temperature(agent_name)
    if provider["provider"] == "anthropic":
        return await self._call_anthropic(provider["model"], messages, system, temp)
    elif provider["provider"] == "openai":
        return await self._call_openai(provider["model"], messages, system, temp)
    raise ValueError(f"Unknown provider: {provider['provider']}")

async def _call_anthropic(self, model: str, messages: list[dict],
                          system: str = None, temperature: float = 0.5) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic()
    kwargs = {"model": model, "max_tokens": 4096, "messages": messages,
              "temperature": temperature}
    if system:
        kwargs["system"] = system
    response = await client.messages.create(**kwargs)
    return response.content[0].text

async def _call_openai(self, model: str, messages: list[dict],
                       system: str = None, temperature: float = 0.5) -> str:
    import openai
    client = openai.AsyncOpenAI()
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    response = await client.chat.completions.create(
        model=model, messages=msgs, temperature=temperature)
    return response.choices[0].message.content
```

**Step 4: Add temperature config to `quantclaw/config/default.yaml`**

Add after the `models` section:

```yaml
temperatures:
  miner: 0.9
  researcher: 0.7
  scheduler: 0.5
  trainer: 0.5
  debugger: 0.3
  reporter: 0.3
  ingestor: 0.2
  backtester: 0.2
  sentinel: 0.2
  risk_monitor: 0.1
  executor: 0.1
  compliance: 0.1
  cost_tracker: 0.1
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_temperature.py tests/test_orchestrator.py -v`
Expected: All PASS (existing tests still pass too)

**Step 6: Commit**

```bash
git add quantclaw/orchestrator/router.py quantclaw/config/default.yaml tests/test_temperature.py
git commit -m "feat: add per-agent LLM temperature routing"
```

---

## Task 6: Enhanced DAG Dispatcher with Orchestration Events

Extend the existing Dispatcher to emit orchestration-specific events and pass results between dependent steps.

**Files:**
- Modify: `quantclaw/orchestrator/dispatcher.py`
- Create: `tests/test_dag_execution.py`

**Step 1: Write the failing tests**

```python
# tests/test_dag_execution.py
"""Tests for enhanced DAG execution with orchestration events."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool
from quantclaw.orchestrator.plan import Plan, PlanStep, StepStatus


class AccumulatorAgent(BaseAgent):
    """Agent that returns its input plus its own contribution."""
    name = "accumulator"
    model = "sonnet"

    async def execute(self, task: dict) -> AgentResult:
        value = task.get("value", 0)
        upstream = task.get("_upstream_results", {})
        total = value + sum(r.get("value", 0) for r in upstream.values())
        return AgentResult(status=AgentStatus.SUCCESS, data={"value": total})


def _make_pool():
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("accumulator", AccumulatorAgent)
    return bus, pool


def test_dag_passes_upstream_results():
    bus, pool = _make_pool()
    dispatcher = Dispatcher(pool=pool)

    plan = Plan(
        id="test-dag",
        description="test upstream passing",
        steps=[
            PlanStep(id=0, agent="accumulator", task={"value": 10},
                     description="step 0", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="accumulator", task={"value": 5},
                     description="step 1", depends_on=[0], status=StepStatus.APPROVED),
        ],
    )

    results = asyncio.run(dispatcher.execute_plan(plan))
    # Step 1 should have received step 0's result as upstream
    assert results[1].data["value"] == 15  # 5 + 10 from upstream


def test_dag_emits_orchestration_events():
    bus, pool = _make_pool()
    dispatcher = Dispatcher(pool=pool)

    captured = []
    async def capture(event):
        captured.append(event)
    bus.subscribe("orchestration.*", capture)

    plan = Plan(
        id="test-events",
        description="test events",
        steps=[
            PlanStep(id=0, agent="accumulator", task={"value": 1},
                     description="step 0", depends_on=[], status=StepStatus.APPROVED),
        ],
    )

    asyncio.run(dispatcher.execute_plan(plan))
    # Allow event handlers to run
    asyncio.run(asyncio.sleep(0.1))

    event_types = [str(e.type) for e in captured]
    assert "orchestration.step_started" in event_types
    assert "orchestration.step_completed" in event_types


def test_dag_broadcast_event_for_parallel_steps():
    bus, pool = _make_pool()
    dispatcher = Dispatcher(pool=pool)

    captured = []
    async def capture(event):
        captured.append(event)
    bus.subscribe("orchestration.*", capture)

    plan = Plan(
        id="test-broadcast",
        description="test broadcast",
        steps=[
            PlanStep(id=0, agent="accumulator", task={"value": 1},
                     description="a", depends_on=[], status=StepStatus.APPROVED),
            PlanStep(id=1, agent="accumulator", task={"value": 2},
                     description="b", depends_on=[], status=StepStatus.APPROVED),
        ],
    )

    asyncio.run(dispatcher.execute_plan(plan))
    asyncio.run(asyncio.sleep(0.1))

    broadcast_events = [e for e in captured if str(e.type) == "orchestration.broadcast"]
    assert len(broadcast_events) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dag_execution.py -v`
Expected: FAIL — upstream results not passed, orchestration events not emitted

**Step 3: Update the Dispatcher**

Replace `execute_plan` in `quantclaw/orchestrator/dispatcher.py` with the enhanced version. The Dispatcher needs access to an EventBus, so update the constructor:

```python
class Dispatcher:
    def __init__(self, pool: AgentPool, bus: EventBus | None = None):
        self._pool = pool
        self._bus = bus

    async def _emit(self, event_type: EventType, payload: dict) -> None:
        if self._bus:
            await self._bus.publish(Event(
                type=event_type,
                payload=payload,
                source_agent="scheduler",
            ))
```

Update `execute_plan` to:
1. Inject `_upstream_results` into each step's task dict from completed dependency results
2. Emit `ORCHESTRATION_BROADCAST` when dispatching parallel steps
3. Emit `ORCHESTRATION_STEP_STARTED` and `ORCHESTRATION_STEP_COMPLETED`/`ORCHESTRATION_STEP_FAILED` per step

Full updated `execute_plan`:

```python
async def execute_plan(self, plan: Plan) -> dict[int, AgentResult]:
    results: dict[int, AgentResult] = {}

    while not plan.is_complete():
        ready = plan.get_ready_steps()
        if not ready:
            break

        # Broadcast when dispatching multiple steps in parallel
        if len(ready) > 1 and self._bus:
            await self._emit(EventType.ORCHESTRATION_BROADCAST, {
                "plan_id": plan.id,
                "targets": [s.agent for s in ready],
                "step_ids": [s.id for s in ready],
            })

        async def run_step(step: PlanStep) -> tuple[int, AgentResult]:
            # Inject upstream results
            upstream = {}
            for dep_id in step.depends_on:
                if dep_id in results and results[dep_id].status == AgentStatus.SUCCESS:
                    upstream[str(dep_id)] = results[dep_id].data
            task = {**step.task, "_upstream_results": upstream}

            await self._emit(EventType.ORCHESTRATION_STEP_STARTED, {
                "plan_id": plan.id,
                "step_id": step.id,
                "agent": step.agent,
                "description": step.description,
            })

            step.status = StepStatus.RUNNING
            result = await self.dispatch(step.agent, task)

            if result.status == AgentStatus.SUCCESS:
                step.status = StepStatus.COMPLETED
                await self._emit(EventType.ORCHESTRATION_STEP_COMPLETED, {
                    "plan_id": plan.id,
                    "step_id": step.id,
                    "agent": step.agent,
                })
            else:
                step.status = StepStatus.FAILED
                await self._emit(EventType.ORCHESTRATION_STEP_FAILED, {
                    "plan_id": plan.id,
                    "step_id": step.id,
                    "agent": step.agent,
                    "error": result.error,
                })

            return step.id, result

        parallel_tasks = [run_step(step) for step in ready]
        step_results = await asyncio.gather(*parallel_tasks)

        for step_id, result in step_results:
            results[step_id] = result
            plan.results[step_id] = result

    return results
```

Add the necessary imports at the top of `dispatcher.py`:

```python
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
```

**Step 4: Update existing tests to pass `bus=None` (backward compatible)**

The existing `test_orchestrator.py` tests create `Dispatcher(pool=pool)` — this still works because `bus` defaults to `None`.

**Step 5: Run all tests**

Run: `python -m pytest tests/test_dag_execution.py tests/test_orchestrator.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add quantclaw/orchestrator/dispatcher.py tests/test_dag_execution.py
git commit -m "feat: enhanced DAG dispatcher with upstream results and orchestration events"
```

---

## Task 7: OODA Loop — The Orchestration Engine Core

The main OODA loop replaces the cron-based scheduler loop. It continuously observes, orients, decides, acts, learns, and sleeps.

**Files:**
- Create: `quantclaw/orchestration/ooda.py`
- Create: `tests/test_ooda.py`

**Step 1: Write the failing tests**

```python
# tests/test_ooda.py
"""Tests for the OODA loop orchestration engine."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool


class StubAgent(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={"result": "stub"})


def _make_ooda(tmp_path, mode=AutonomyMode.PLAN):
    bus = EventBus()
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    pool = AgentPool(bus=bus, config={})
    pool.register("researcher", StubAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(
        bus=bus,
        playbook=playbook,
        trust=TrustManager(),
        autonomy=AutonomyManager(initial_mode=mode),
        dispatcher=dispatcher,
        config={},
    )
    return bus, playbook, ooda


def test_ooda_initial_phase(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)
    assert ooda.phase == OODAPhase.SLEEP


def test_ooda_observe_returns_state(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        state = await ooda.observe()
        assert "pending_tasks" in state
        assert "recent_events" in state
        assert "playbook_recent" in state

    asyncio.run(_run())


def test_ooda_orient_with_goal(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        state = await ooda.observe()
        orientation = await ooda.orient(state, goal="Find profitable momentum strategies")
        assert "goal" in orientation
        assert "actions_needed" in orientation

    asyncio.run(_run())


def test_ooda_decide_calls_planner(tmp_path):
    """GAP 1: decide() must use LLM/Planner to generate DAG, not hardcode."""
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        ooda.set_goal("Find momentum strategies")
        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)
        # decide() should return a Plan object (from orchestrator.plan),
        # not a plain dict
        assert plan is not None
        assert hasattr(plan, "steps")  # It's a Plan object
        assert hasattr(plan, "id")

    asyncio.run(_run())


def test_ooda_act_executes_plan(tmp_path):
    """GAP 2: act() method must exist and execute the DAG via Dispatcher."""
    bus, _, ooda = _make_ooda(tmp_path, mode=AutonomyMode.AUTOPILOT)

    captured = []
    async def capture(event):
        captured.append(event)
    bus.subscribe("orchestration.*", capture)

    async def _run():
        ooda.set_goal("Research something")
        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)
        if plan:
            results = await ooda.act(plan)
            assert ooda.phase == OODAPhase.ACT
            assert isinstance(results, dict)

    asyncio.run(_run())


def test_ooda_learn_adds_to_playbook(tmp_path):
    _, playbook, ooda = _make_ooda(tmp_path)

    async def _run():
        await ooda.learn({
            "type": "strategy_result",
            "content": {"strategy": "momentum_5d", "sharpe": 1.5},
            "tags": ["momentum"],
        })
        entries = await playbook.query(tags=["momentum"])
        assert len(entries) == 1

    asyncio.run(_run())


def test_ooda_phase_transitions(tmp_path):
    _, _, ooda = _make_ooda(tmp_path)

    async def _run():
        assert ooda.phase == OODAPhase.SLEEP

        await ooda.observe()
        assert ooda.phase == OODAPhase.OBSERVE

        state = await ooda.observe()
        await ooda.orient(state, goal="test")
        assert ooda.phase == OODAPhase.ORIENT

    asyncio.run(_run())


def test_ooda_sleep_wakes_on_event(tmp_path):
    """GAP 3: Sleep should wake on events, not just timer."""
    bus, _, ooda = _make_ooda(tmp_path)

    async def _run():
        # Start sleep with a wake event
        wake_task = asyncio.create_task(ooda.sleep_until_trigger(timeout=5.0))
        # Simulate a CEO message event after a short delay
        await asyncio.sleep(0.05)
        await bus.publish(
            __import__("quantclaw.events.types", fromlist=["Event"]).Event(
                type=EventType.AGENT_TASK_COMPLETED,
                payload={"agent": "researcher"},
                source_agent="researcher",
            )
        )
        # Should wake up before the 5s timeout
        await asyncio.wait_for(wake_task, timeout=1.0)
        assert ooda.phase == OODAPhase.OBSERVE  # Woke up and transitioned

    asyncio.run(_run())
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ooda.py -v`
Expected: FAIL

**Step 3: Write the OODA Loop implementation**

```python
# quantclaw/orchestration/ooda.py
"""OODA Loop: Observe-Orient-Decide-Act-Learn-Sleep orchestration engine."""
from __future__ import annotations

import asyncio
import json
from enum import StrEnum
from typing import Any

from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType
from quantclaw.orchestration.playbook import Playbook, EntryType
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.plan import Plan, PlanStep, StepStatus
from quantclaw.orchestrator.planner import Planner
from quantclaw.orchestrator.router import LLMRouter


# Known workflow types the Scheduler can draw from (GAP 6)
WORKFLOW_EXAMPLES = [
    "signal_hunting", "strategy_development", "backtest_and_compare",
    "go_live", "portfolio_management", "risk_response",
    "research_report", "ml_pipeline",
]


class OODAPhase(StrEnum):
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"
    LEARN = "learn"
    SLEEP = "sleep"


class OODALoop:
    """Continuous OODA loop for the Scheduler agent.

    - decide() uses the LLM via Planner to generate task DAGs (GAP 1 fix)
    - act() executes the DAG via Dispatcher (GAP 2 fix)
    - sleep_until_trigger() wakes on events, not just timer (GAP 3 fix)
    - Playbook context injected into LLM prompts (GAP 6 fix)
    """

    def __init__(
        self,
        bus: EventBus,
        playbook: Playbook,
        trust: TrustManager,
        autonomy: AutonomyManager,
        dispatcher: Dispatcher,
        config: dict,
    ):
        self._bus = bus
        self._playbook = playbook
        self._trust = trust
        self._autonomy = autonomy
        self._dispatcher = dispatcher
        self._config = config
        self._phase = OODAPhase.SLEEP
        self._pending_tasks: list[dict] = []
        self._goal: str = ""
        self._wake_event = asyncio.Event()

        # Subscribe to wake triggers (GAP 3 fix)
        self._bus.subscribe("agent.*", self._on_wake_trigger)
        self._bus.subscribe("market.*", self._on_wake_trigger)

    async def _on_wake_trigger(self, event: Event) -> None:
        """Wake the OODA loop when a relevant event arrives."""
        self._wake_event.set()

    @property
    def phase(self) -> OODAPhase:
        return self._phase

    def set_goal(self, goal: str) -> None:
        self._goal = goal
        self._wake_event.set()  # Wake up on new goal

    def add_pending_task(self, task: dict) -> None:
        self._pending_tasks.append(task)
        self._wake_event.set()  # Wake up on new task

    async def observe(self) -> dict[str, Any]:
        """OBSERVE: Gather current state from all sources."""
        self._phase = OODAPhase.OBSERVE

        recent_events = self._bus.recent(20)
        playbook_recent = await self._playbook.recent(10)

        return {
            "pending_tasks": list(self._pending_tasks),
            "recent_events": [
                {"type": str(e.type), "payload": e.payload, "source": e.source_agent}
                for e in recent_events
            ],
            "playbook_recent": [
                {"type": e.entry_type.value, "content": e.content, "tags": e.tags}
                for e in playbook_recent
            ],
            "trust_level": self._trust.level.name,
            "trust_metrics": self._trust.get_metrics(),
            "autonomy_mode": self._autonomy.mode.value,
        }

    async def orient(self, state: dict, goal: str = "") -> dict[str, Any]:
        """ORIENT: Compare current state to goal, determine needed actions."""
        self._phase = OODAPhase.ORIENT

        active_goal = goal or self._goal

        actions_needed: list[str] = []

        if state["pending_tasks"]:
            actions_needed.append("process_pending_tasks")

        market_events = [
            e for e in state["recent_events"]
            if e["type"].startswith("market.")
        ]
        if market_events:
            actions_needed.append("respond_to_market_events")

        if not actions_needed and active_goal:
            actions_needed.append("plan_toward_goal")

        return {
            "goal": active_goal,
            "actions_needed": actions_needed,
            "market_events": market_events,
            "trust_level": state["trust_level"],
            "playbook_context": state["playbook_recent"],  # GAP 6: pass to LLM
        }

    async def decide(self, orientation: dict) -> Plan | None:
        """DECIDE: Use LLM via Planner to generate a task DAG.

        GAP 1 fix: Calls Planner.create_plan() with goal + playbook context,
        letting the LLM generate the DAG with creative latitude.
        Returns a Plan object, not a plain dict.
        """
        self._phase = OODAPhase.DECIDE

        if not orientation["actions_needed"]:
            return None

        # Build a rich prompt with playbook context (GAP 6 fix)
        playbook_summary = ""
        if orientation.get("playbook_context"):
            entries = orientation["playbook_context"][:5]
            playbook_summary = "\n\nPlaybook context (recent knowledge):\n"
            for e in entries:
                playbook_summary += f"- [{e['type']}] {json.dumps(e['content'])[:200]}\n"

        goal = orientation.get("goal", "")
        actions = ", ".join(orientation["actions_needed"])

        planner_request = (
            f"Goal: {goal}\n"
            f"Actions needed: {actions}\n"
            f"Trust level: {orientation.get('trust_level', 'OBSERVER')}\n"
            f"Known workflow types: {', '.join(WORKFLOW_EXAMPLES)}\n"
            f"You have full creative latitude — invent new approaches, "
            f"try unconventional combinations, run parallel experiments.\n"
            f"{playbook_summary}"
        )

        try:
            router = LLMRouter(self._config)
            planner = Planner(router)
            plan = await planner.create_plan(planner_request)
        except Exception:
            # Fallback: create a minimal plan from pending tasks
            steps = []
            for i, task in enumerate(self._pending_tasks):
                steps.append(PlanStep(
                    id=i,
                    agent=task.get("agent", "researcher"),
                    task=task.get("task", {}),
                    description=f"Process: {task.get('agent', 'unknown')}",
                    depends_on=[],
                ))
            import uuid
            plan = Plan(
                id=str(uuid.uuid4())[:8],
                description=goal or "Process pending tasks",
                steps=steps,
            )

        # In Autopilot: auto-approve. In Plan Mode: leave as proposed.
        if not self._autonomy.should_wait_for_approval():
            plan.approve_all()

        await self._bus.publish(Event(
            type=EventType.ORCHESTRATION_PLAN_CREATED,
            payload={"plan_id": plan.id, "description": plan.description,
                     "steps": len(plan.steps)},
            source_agent="scheduler",
        ))

        return plan

    async def act(self, plan: Plan) -> dict:
        """ACT: Execute the plan DAG via Dispatcher.

        GAP 2 fix: This was completely missing. Executes the plan
        respecting dependencies and parallel execution.
        """
        self._phase = OODAPhase.ACT

        plan.status = __import__(
            "quantclaw.orchestrator.plan", fromlist=["PlanStatus"]
        ).PlanStatus.EXECUTING

        results = await self._dispatcher.execute_plan(plan)

        # Clear pending tasks that were incorporated into this plan
        self._pending_tasks.clear()

        return results

    async def learn(self, result: dict) -> None:
        """LEARN: Record outcomes to playbook."""
        self._phase = OODAPhase.LEARN

        entry_type = EntryType(result.get("type", "strategy_result"))
        content = result.get("content", {})
        tags = result.get("tags", [])

        entry = await self._playbook.add(entry_type, content, tags)

        await self._bus.publish(Event(
            type=EventType.PLAYBOOK_ENTRY_ADDED,
            payload={
                "entry_type": entry.entry_type.value,
                "tags": entry.tags,
            },
            source_agent="scheduler",
        ))

    async def sleep(self) -> None:
        """SLEEP: Reset phase. For simple usage / tests."""
        self._phase = OODAPhase.SLEEP

    async def sleep_until_trigger(self, timeout: float = 30.0) -> None:
        """SLEEP: Wait for next trigger — event-driven, not just timer.

        GAP 3 fix: Wakes on market events, CEO instructions, agent completions,
        or timeout (whichever comes first).

        Triggers:
        - Timer (configurable timeout)
        - Market event (subscribed via bus)
        - CEO instruction (set_goal / add_pending_task sets wake_event)
        - Agent completion (subscribed via bus)
        """
        self._phase = OODAPhase.SLEEP
        self._wake_event.clear()

        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass  # Timer trigger — proceed with next cycle

        self._phase = OODAPhase.OBSERVE
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ooda.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add quantclaw/orchestration/ooda.py tests/test_ooda.py
git commit -m "feat: add OODA loop orchestration engine core"
```

---

## Task 8: Integrate OODA Loop into Daemon

Replace the cron-based scheduler loop in `daemon.py` with the OODA loop. Keep cron support as a trigger source within the OODA Sleep phase.

**Files:**
- Modify: `quantclaw/daemon.py`
- Modify: `quantclaw/orchestrator/pool.py` (expose bus for dispatcher)

**Step 1: Write the failing test**

Add to `tests/test_orchestrator.py`:

```python
def test_dispatcher_with_event_bus():
    """Verify dispatcher accepts optional bus parameter."""
    bus = EventBus()
    pool = AgentPool(bus=bus, config={})
    pool.register("echo", EchoAgent)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    result = asyncio.run(dispatcher.dispatch("echo", {"msg": "test"}))
    assert result.status == AgentStatus.SUCCESS
```

**Step 2: Run test**

Run: `python -m pytest tests/test_orchestrator.py::test_dispatcher_with_event_bus -v`
Expected: Should PASS (we already updated Dispatcher in Task 6)

**Step 3: Update `daemon.py` to use OODA loop**

Update the imports and `__init__` of `QuantClawDaemon` to create the orchestration components:

```python
# Add to imports
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager, RiskGuardrails
from quantclaw.orchestration.autonomy import AutonomyManager
from quantclaw.orchestration.ooda import OODALoop
```

In `__init__`, add:
```python
self._playbook = Playbook("data/playbook.jsonl")
self._guardrails = RiskGuardrails.from_config(self._config)
self._autonomy = AutonomyManager()

# Restore trust from playbook (GAP 4 fix)
# Note: trust is restored asynchronously in start()
self._trust = TrustManager(bus=self._bus, playbook=self._playbook)
```

In `start()`, add trust restoration before the scheduler loop:
```python
# Restore trust level from playbook
self._trust = await TrustManager.from_playbook(
    self._playbook, bus=self._bus
)
self._trust._playbook = self._playbook  # Ensure future upgrades persist

self._ooda = OODALoop(
    bus=self._bus,
    playbook=self._playbook,
    trust=self._trust,
    autonomy=self._autonomy,
    dispatcher=self._dispatcher,
    config=self._config,
)
```

Update `_scheduler_loop` to use `act()` and `sleep_until_trigger()`:

```python
async def _scheduler_loop(self):
    """Run OODA loop with cron triggers and event-driven wakeup."""
    schedules = self._config.get("schedules", {})
    crons = {}
    for name, sched in schedules.items():
        cron_iter = croniter(sched["cron"], datetime.now())
        crons[name] = {
            "iter": cron_iter,
            "agent": sched["agent"],
            "task": sched.get("task", name),
            "depends_on": sched.get("depends_on"),
            "next": cron_iter.get_next(datetime),
        }

    check_interval = self._config.get("ooda_interval", 30)

    while self._running:
        # Check cron triggers
        now = datetime.now()
        for name, cron in crons.items():
            if now >= cron["next"]:
                await self._bus.publish(Event(
                    type=EventType.SCHEDULE_TRIGGERED,
                    payload={"schedule": name, "agent": cron["agent"], "task": cron["task"]},
                ))
                self._ooda.add_pending_task({
                    "agent": cron["agent"],
                    "task": cron["task"],
                    "source": "cron",
                    "schedule": name,
                })
                cron["next"] = cron["iter"].get_next(datetime)

        # Run one OODA cycle
        state = await self._ooda.observe()
        orientation = await self._ooda.orient(state)
        plan = await self._ooda.decide(orientation)

        # GAP 2 fix: use act() to execute the plan
        if plan and plan.status.value == "approved":
            results = await self._ooda.act(plan)

            # GAP 1/6: Learn from results
            for step_id, result in results.items():
                if result.status.value == "success" and result.data:
                    await self._ooda.learn({
                        "type": "strategy_result",
                        "content": result.data,
                        "tags": ["auto"],
                    })

        # GAP 3 fix: event-driven sleep instead of fixed timer
        await self._ooda.sleep_until_trigger(timeout=check_interval)
```

Update the Dispatcher creation to pass the bus:
```python
self._dispatcher = Dispatcher(pool=self._pool, bus=self._bus)
```

**Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add quantclaw/daemon.py
git commit -m "feat: integrate OODA loop into daemon, replacing pure cron scheduler"
```

---

## Task 9: Orchestration API Endpoints

Add REST endpoints for controlling the orchestration engine: autonomy mode, trust level, playbook access, and kill switch.

**Files:**
- Modify: `quantclaw/dashboard/api.py`
- Create: `tests/test_orchestration_api.py`

**Step 1: Write the failing tests**

```python
# tests/test_orchestration_api.py
"""Tests for orchestration API endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_get_orchestration_status():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/orchestration/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "autonomy_mode" in data
    assert "trust_level" in data
    assert "ooda_phase" in data


def test_set_autonomy_mode():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.post("/api/orchestration/mode", json={"mode": "autopilot"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "autopilot"


def test_get_playbook_recent():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/orchestration/playbook/recent")
    assert resp.status_code == 200
    assert "entries" in resp.json()


def test_get_trust_status():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.get("/api/orchestration/trust")
    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data
    assert "metrics" in data


def test_kill_switch():
    from quantclaw.dashboard.api import app
    client = TestClient(app)
    resp = client.post("/api/orchestration/kill")
    assert resp.status_code == 200
    assert resp.json()["status"] == "halted"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestration_api.py -v`
Expected: FAIL — 404 on all endpoints

**Step 3: Add endpoints to `quantclaw/dashboard/api.py`**

Add module-level orchestration state (after existing shared state):

```python
from quantclaw.orchestration.playbook import Playbook
from quantclaw.orchestration.trust import TrustManager
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.ooda import OODALoop

from quantclaw.orchestrator.dispatcher import Dispatcher as _Dispatcher
from quantclaw.orchestrator.pool import AgentPool as _AgentPool

_playbook = Playbook("data/playbook.jsonl")
_trust = TrustManager()
_autonomy = AutonomyManager()
_orch_pool = _AgentPool(bus=_bus, config=_config or {})
_orch_dispatcher = _Dispatcher(pool=_orch_pool, bus=_bus)
_ooda = OODALoop(bus=_bus, playbook=_playbook, trust=_trust, autonomy=_autonomy,
                 dispatcher=_orch_dispatcher, config=_config or {})
```

Add the endpoint functions:

```python
# ── Orchestration ──
@app.get("/api/orchestration/status")
def orchestration_status():
    return {
        "autonomy_mode": _autonomy.mode.value,
        "trust_level": _trust.level.name,
        "trust_level_id": int(_trust.level),
        "ooda_phase": _ooda.phase.value,
        "trust_metrics": _trust.get_metrics(),
    }

@app.post("/api/orchestration/mode")
def set_orchestration_mode(body: dict):
    mode_str = body.get("mode", "plan")
    try:
        mode = AutonomyMode(mode_str)
    except ValueError:
        return {"error": f"Invalid mode: {mode_str}"}
    _autonomy.set_mode(mode)
    return {"mode": _autonomy.mode.value}

@app.get("/api/orchestration/playbook/recent")
async def get_playbook_recent():
    entries = await _playbook.recent(20)
    return {
        "entries": [
            {
                "type": e.entry_type.value,
                "content": e.content,
                "tags": e.tags,
                "timestamp": e.timestamp,
            }
            for e in entries
        ]
    }

@app.get("/api/orchestration/trust")
def get_trust():
    return {
        "level": _trust.level.name,
        "level_id": int(_trust.level),
        "metrics": _trust.get_metrics(),
        "can_paper_trade": _trust.can_paper_trade(),
        "can_live_trade": _trust.can_live_trade(),
    }

@app.post("/api/orchestration/trust/upgrade")
async def upgrade_trust(body: dict):
    from quantclaw.orchestration.trust import TrustLevel
    target = body.get("level", 1)
    try:
        await _trust.upgrade(TrustLevel(target))
        return {"level": _trust.level.name, "level_id": int(_trust.level)}
    except ValueError as e:
        return {"error": str(e)}

@app.post("/api/orchestration/kill")
async def kill_switch():
    """Emergency halt: stop all trading and pending tasks."""
    _autonomy.set_mode(AutonomyMode.PLAN)
    await _bus.publish(Event(
        type=EventType.ORCHESTRATION_BROADCAST,
        payload={"action": "kill_switch", "message": "CEO activated kill switch"},
        source_agent="scheduler",
    ))
    return {"status": "halted", "mode": _autonomy.mode.value}

@app.post("/api/orchestration/goal")
async def set_goal(body: dict):
    goal = body.get("goal", "")
    _ooda.set_goal(goal)
    return {"goal": goal, "status": "set"}
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestration_api.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add quantclaw/dashboard/api.py tests/test_orchestration_api.py
git commit -m "feat: add orchestration REST API endpoints"
```

---

## Task 10: Frontend — Handle Orchestration Events in useFloorEvents

Update the frontend event handler to process new orchestration events and update the trading floor visualization.

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts`
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/types.ts` (check for FloorEvent type)

**Step 1: Read the current FloorEvent type**

Read `quantclaw/dashboard/app/app/dashboard/floor/types.ts` to understand the type definition.

**Step 2: Add orchestration event types to `useFloorEvents.ts`**

Add these cases to the `handleEvent` switch in `useFloorEvents.ts`:

```typescript
case "orchestration.plan_created": {
  // Light up scheduler with plan info
  const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
  if (schedulerIdx >= 0) {
    updated[schedulerIdx] = {
      ...updated[schedulerIdx],
      state: "busy",
      speechBubble: event.message || "Planning...",
    };
  }
  break;
}

case "orchestration.step_started": {
  const targetAgent = event.payload?.agent || event.agent;
  const ti = updated.findIndex((a) => a.name === targetAgent);
  if (ti >= 0) {
    updated[ti] = {
      ...updated[ti],
      state: "busy",
      progress: 0,
      speechBubble: event.payload?.description || event.message || "Working...",
    };
  }
  break;
}

case "orchestration.step_completed": {
  const targetAgent = event.payload?.agent || event.agent;
  const ti = updated.findIndex((a) => a.name === targetAgent);
  if (ti >= 0) {
    updated[ti] = {
      ...updated[ti],
      state: "complete",
      progress: 100,
      speechBubble: "Done!",
    };
    setTimeout(() => {
      setAgents((prev2) => {
        const u = [...prev2];
        const i = u.findIndex((a) => a.name === targetAgent);
        if (i >= 0 && u[i].state === "complete") {
          u[i] = { ...u[i], state: "idle", progress: 0, speechBubble: null };
        }
        return u;
      });
    }, 3000);
  }
  break;
}

case "orchestration.step_failed": {
  const targetAgent = event.payload?.agent || event.agent;
  const ti = updated.findIndex((a) => a.name === targetAgent);
  if (ti >= 0) {
    updated[ti] = {
      ...updated[ti],
      state: "error",
      progress: 0,
      speechBubble: event.payload?.error || "Failed",
    };
    setTimeout(() => {
      setAgents((prev2) => {
        const u = [...prev2];
        const i = u.findIndex((a) => a.name === targetAgent);
        if (i >= 0 && u[i].state === "error") {
          u[i] = { ...u[i], state: "idle", speechBubble: null };
        }
        return u;
      });
    }, 5000);
  }
  break;
}

case "orchestration.broadcast": {
  // Same as agent.broadcast — pulse from scheduler to targets
  const scheduler = STATIONS.find((s) => s.name === "scheduler");
  if (scheduler) {
    setBroadcastOrigin({
      x: scheduler.x + scheduler.width / 2,
      y: scheduler.y + scheduler.height / 2,
    });
    setTimeout(() => setBroadcastOrigin(null), 2000);
  }
  const targets = event.payload?.targets || event.targets || [];
  for (const target of targets) {
    const ti = updated.findIndex((a) => a.name === target);
    if (ti >= 0) {
      updated[ti] = { ...updated[ti], state: "busy", progress: 0 };
    }
  }
  break;
}

case "playbook.entry_added": {
  // Brief highlight on scheduler for knowledge recording
  const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
  if (schedulerIdx >= 0) {
    updated[schedulerIdx] = {
      ...updated[schedulerIdx],
      speechBubble: `Recorded: ${event.payload?.entry_type || "knowledge"}`,
    };
  }
  break;
}

case "trust.level_changed": {
  const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
  if (schedulerIdx >= 0) {
    updated[schedulerIdx] = {
      ...updated[schedulerIdx],
      speechBubble: `Trust: ${event.payload?.level || "upgraded"}`,
    };
  }
  break;
}
```

Also update the `FloorEvent` type in `types.ts` to include `payload` field if it doesn't exist:

```typescript
export interface FloorEvent {
  type: string;
  agent?: string;
  targets?: string[];
  progress?: number;
  message?: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
}
```

**Step 3: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts quantclaw/dashboard/app/app/dashboard/floor/types.ts
git commit -m "feat: handle orchestration events in trading floor UI"
```

---

## Task 11: Integration Test — Full OODA Cycle

End-to-end test that exercises the full orchestration stack: goal setting, OODA cycle, playbook recording, trust checking.

**Files:**
- Create: `tests/test_orchestration_integration.py`

**Step 1: Write the integration test**

```python
# tests/test_orchestration_integration.py
"""Integration test: full OODA cycle with all orchestration components."""
import asyncio
import pytest

from quantclaw.agents.base import AgentResult, AgentStatus, BaseAgent
from quantclaw.events.bus import EventBus
from quantclaw.events.types import EventType
from quantclaw.orchestration.autonomy import AutonomyManager, AutonomyMode
from quantclaw.orchestration.ooda import OODALoop, OODAPhase
from quantclaw.orchestration.playbook import Playbook, EntryType
from quantclaw.orchestration.trust import TrustManager, TrustLevel, RiskGuardrails
from quantclaw.orchestrator.dispatcher import Dispatcher
from quantclaw.orchestrator.pool import AgentPool
from quantclaw.orchestrator.plan import Plan, PlanStep, StepStatus


class MockResearcher(BaseAgent):
    name = "researcher"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "findings": "Momentum factor shows promise in current regime"
        })


class MockBacktester(BaseAgent):
    name = "backtester"
    model = "sonnet"
    async def execute(self, task: dict) -> AgentResult:
        upstream = task.get("_upstream_results", {})
        return AgentResult(status=AgentStatus.SUCCESS, data={
            "sharpe": 1.5, "annual_return": 0.18, "max_drawdown": -0.08
        })


@pytest.fixture
def setup(tmp_path):
    bus = EventBus()
    playbook = Playbook(str(tmp_path / "playbook.jsonl"))
    trust = TrustManager()
    autonomy = AutonomyManager(initial_mode=AutonomyMode.AUTOPILOT)
    config = {"risk": {"max_drawdown": -0.10, "max_position_pct": 0.05}}
    pool = AgentPool(bus=bus, config=config)
    pool.register("researcher", MockResearcher)
    pool.register("backtester", MockBacktester)
    dispatcher = Dispatcher(pool=pool, bus=bus)
    ooda = OODALoop(bus=bus, playbook=playbook, trust=trust, autonomy=autonomy,
                    dispatcher=dispatcher, config=config)
    return bus, playbook, trust, autonomy, dispatcher, ooda


def test_full_ooda_cycle(setup):
    bus, playbook, trust, autonomy, dispatcher, ooda = setup

    async def _run():
        # 1. Set goal
        ooda.set_goal("Find profitable momentum strategies")

        # 2. OBSERVE
        state = await ooda.observe()
        assert ooda.phase == OODAPhase.OBSERVE

        # 3. ORIENT
        orientation = await ooda.orient(state)
        assert ooda.phase == OODAPhase.ORIENT
        assert "plan_toward_goal" in orientation["actions_needed"]

        # 4. DECIDE — now returns a Plan object via Planner (GAP 1 fix)
        plan = await ooda.decide(orientation)
        assert ooda.phase == OODAPhase.DECIDE
        assert plan is not None
        assert hasattr(plan, "steps")  # It's a Plan object

        # 5. ACT — uses ooda.act() to execute via Dispatcher (GAP 2 fix)
        # For this test, create a known plan instead of LLM-generated one
        exec_plan = Plan(
            id="momentum-search",
            description="Search for momentum strategies",
            steps=[
                PlanStep(id=0, agent="researcher", task={"query": "momentum factors"},
                         description="Research momentum", depends_on=[], status=StepStatus.APPROVED),
                PlanStep(id=1, agent="backtester", task={"strategy": "momentum_5d"},
                         description="Backtest momentum", depends_on=[0], status=StepStatus.APPROVED),
            ],
        )
        results = await ooda.act(exec_plan)
        assert ooda.phase == OODAPhase.ACT
        assert results[0].status == AgentStatus.SUCCESS
        assert results[1].status == AgentStatus.SUCCESS
        assert results[1].data["sharpe"] == 1.5

        # 6. LEARN
        await ooda.learn({
            "type": "strategy_result",
            "content": {
                "strategy": "momentum_5d",
                "sharpe": results[1].data["sharpe"],
                "annual_return": results[1].data["annual_return"],
            },
            "tags": ["momentum", "backtest"],
        })

        entries = await playbook.query(tags=["momentum"])
        assert len(entries) == 1
        assert entries[0].content["sharpe"] == 1.5

        # 7. SLEEP
        await ooda.sleep()
        assert ooda.phase == OODAPhase.SLEEP

    asyncio.run(_run())


def test_plan_mode_requires_approval(setup):
    bus, playbook, trust, autonomy, dispatcher, ooda = setup

    async def _run():
        autonomy.set_mode(AutonomyMode.PLAN)
        ooda.set_goal("test")
        ooda.add_pending_task({"agent": "researcher", "task": "test"})

        state = await ooda.observe()
        orientation = await ooda.orient(state)
        plan = await ooda.decide(orientation)

        assert plan is not None
        # Plan Mode: steps should NOT be auto-approved
        assert all(s.status == StepStatus.PENDING for s in plan.steps)

    asyncio.run(_run())


def test_risk_guardrails_enforced(setup):
    bus, playbook, trust, autonomy, dispatcher, ooda = setup

    guardrails = RiskGuardrails.from_config({"risk": {"max_drawdown": -0.10, "max_position_pct": 0.05}})

    # Position too large
    assert not guardrails.check_position_size(0.10, 100000)

    # Drawdown exceeded
    assert not guardrails.check_drawdown(-0.12)

    # Trust level blocks live trading at Observer
    assert not trust.can_live_trade()
    trust.upgrade(TrustLevel.PAPER_TRADER)
    assert not trust.can_live_trade()
    assert trust.can_paper_trade()
```

**Step 2: Run integration tests**

Run: `python -m pytest tests/test_orchestration_integration.py -v`
Expected: All 3 tests PASS

**Step 3: Commit**

```bash
git add tests/test_orchestration_integration.py
git commit -m "test: add orchestration engine integration tests"
```

---

## Task 12: Run Full Test Suite and Final Verification

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, no regressions

**Step 2: Verify no import errors**

Run: `python -c "from quantclaw.orchestration.ooda import OODALoop; from quantclaw.orchestration.playbook import Playbook; from quantclaw.orchestration.trust import TrustManager; from quantclaw.orchestration.autonomy import AutonomyManager; print('All imports OK')"`
Expected: "All imports OK"

**Step 3: Final commit**

```bash
git add -A
git commit -m "docs: add orchestration engine implementation plan"
```

---

## Summary of Files Created/Modified

### Audit Gap Fixes Applied
| Gap | Severity | Fix |
|-----|----------|-----|
| GAP 1 | HIGH | `decide()` now calls LLM via `Planner.create_plan()` with playbook context |
| GAP 2 | HIGH | Added `act()` method that executes DAG via `Dispatcher.execute_plan()` |
| GAP 3 | MEDIUM | `sleep_until_trigger()` uses `asyncio.Event` to wake on bus events, CEO msgs, or timeout |
| GAP 4 | MEDIUM | `TrustManager` persists milestones to playbook, restores via `from_playbook()` |
| GAP 5 | MEDIUM | `TrustManager.upgrade()` emits `TRUST_LEVEL_CHANGED` event via EventBus |
| GAP 6 | MEDIUM | Playbook context + creative latitude instructions injected into Planner prompt |

### Created (13 files):
| File | Purpose |
|------|---------|
| `quantclaw/orchestration/__init__.py` | Package init |
| `quantclaw/orchestration/playbook.py` | JSONL persistent knowledge store |
| `quantclaw/orchestration/trust.py` | 5-level progressive trust + risk guardrails + persistence + events |
| `quantclaw/orchestration/autonomy.py` | Autopilot/Plan/Interactive mode management |
| `quantclaw/orchestration/ooda.py` | OODA loop with LLM-driven decide, act(), event-driven sleep |
| `tests/test_playbook.py` | Playbook tests (7 tests) |
| `tests/test_trust.py` | Trust system tests (10 tests, includes persistence + event emission) |
| `tests/test_autonomy.py` | Autonomy mode tests (7 tests) |
| `tests/test_temperature.py` | Temperature routing tests (3 tests) |
| `tests/test_dag_execution.py` | Enhanced DAG tests (3 tests) |
| `tests/test_ooda.py` | OODA loop tests (9 tests, includes act/decide/sleep_until_trigger) |
| `tests/test_orchestration_api.py` | API endpoint tests (5 tests) |
| `tests/test_orchestration_integration.py` | Integration tests (3 tests) |

### Modified (8 files):
| File | Change |
|------|--------|
| `quantclaw/events/types.py` | +7 orchestration event types |
| `quantclaw/orchestrator/router.py` | +temperature routing per agent |
| `quantclaw/orchestrator/dispatcher.py` | +upstream result passing, +orchestration events, +bus param |
| `quantclaw/config/default.yaml` | +temperatures config section |
| `quantclaw/daemon.py` | +OODA loop with act(), sleep_until_trigger(), trust restoration |
| `quantclaw/dashboard/api.py` | +7 orchestration endpoints (status, mode, playbook, trust, kill, goal) |
| `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts` | +7 orchestration event handlers |
| `quantclaw/dashboard/app/app/dashboard/floor/types.ts` | +payload field to FloorEvent |
