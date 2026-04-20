"""Typed event definitions."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

class EventType(StrEnum):
    MARKET_GAP_DETECTED = "market.gap_detected"
    MARKET_REGIME_CHANGE = "market.regime_change"
    TRADE_ORDER_SUBMITTED = "trade.order_submitted"
    TRADE_ORDER_FILLED = "trade.order_filled"
    TRADE_RECONCILIATION_FAIL = "trade.reconciliation_fail"
    PIPELINE_INGESTION_DONE = "pipeline.ingestion_done"
    PIPELINE_INGESTION_FAILED = "pipeline.ingestion_failed"
    PIPELINE_BACKTEST_DONE = "pipeline.backtest_done"
    FACTOR_DECAY_DETECTED = "factor.decay_detected"
    FACTOR_MINING_COMPLETE = "factor.mining_complete"
    AGENT_TASK_STARTED = "agent.task_started"
    AGENT_TASK_COMPLETED = "agent.task_completed"
    AGENT_TASK_FAILED = "agent.task_failed"
    SCHEDULE_TRIGGERED = "schedule.triggered"
    COST_BUDGET_WARNING = "cost.budget_warning"
    TRUST_LEVEL_CHANGED = "trust.level_changed"

    # Orchestration engine events
    ORCHESTRATION_PLAN_CREATED = "orchestration.plan_created"
    ORCHESTRATION_STEP_STARTED = "orchestration.step_started"
    ORCHESTRATION_STEP_COMPLETED = "orchestration.step_completed"
    ORCHESTRATION_STEP_FAILED = "orchestration.step_failed"
    ORCHESTRATION_BROADCAST = "orchestration.broadcast"
    PLAYBOOK_ENTRY_ADDED = "playbook.entry_added"
    CHAT_NARRATIVE = "chat.narrative"
    ORCHESTRATION_CYCLE_COMPLETE = "orchestration.cycle_complete"
    ORCHESTRATION_EVALUATION = "orchestration.evaluation"
    ORCHESTRATION_CAMPAIGN_UPDATED = "orchestration.campaign_updated"
    ORCHESTRATION_ALLOCATION_UPDATED = "orchestration.allocation_updated"

@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    source_agent: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
