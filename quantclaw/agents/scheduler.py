"""Scheduler: cron-based task firing, replaces Windows Task Scheduler."""
from __future__ import annotations

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus


class SchedulerAgent(BaseAgent):
    name = "scheduler"
    model = "sonnet"
    daemon = True

    async def execute(self, task: dict) -> AgentResult:
        # Scheduler logic is in daemon.py's _scheduler_loop
        # This agent exists for registration and event handling
        return AgentResult(status=AgentStatus.SUCCESS)
