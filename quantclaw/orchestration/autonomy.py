"""Autonomy mode management: Autopilot, Plan Mode, Interactive."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING

from quantclaw.orchestration.trust import SAFETY_CRITICAL_ACTIONS

if TYPE_CHECKING:
    from quantclaw.orchestration.playbook import Playbook


class AutonomyMode(StrEnum):
    AUTOPILOT = "autopilot"
    PLAN = "plan"
    INTERACTIVE = "interactive"


class AutonomyManager:
    """Controls how the Scheduler executes plans."""

    def __init__(self, initial_mode: AutonomyMode = AutonomyMode.PLAN,
                 playbook: Playbook | None = None):
        self._mode = initial_mode
        self._playbook = playbook
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

    async def set_mode_persistent(self, mode: AutonomyMode) -> None:
        """Set mode and persist to playbook."""
        self.set_mode(mode)
        if self._playbook:
            from quantclaw.orchestration.playbook import EntryType
            await self._playbook.add(EntryType.CEO_PREFERENCE, {
                "autonomy_mode": mode.value,
            })

    @classmethod
    async def from_playbook(cls, playbook: Playbook) -> AutonomyManager:
        """Restore autonomy mode from playbook."""
        from quantclaw.orchestration.playbook import EntryType
        entries = await playbook.query(entry_type=EntryType.CEO_PREFERENCE)
        mode = AutonomyMode.PLAN
        for entry in reversed(entries):
            if "autonomy_mode" in entry.content:
                try:
                    mode = AutonomyMode(entry.content["autonomy_mode"])
                except ValueError:
                    pass
                break
        return cls(initial_mode=mode, playbook=playbook)
