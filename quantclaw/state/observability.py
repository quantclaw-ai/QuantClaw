"""Agent observability: track tokens, costs, execution time per agent run."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ToolCall:
    tool_name: str
    input_summary: str
    output_summary: str
    duration_ms: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ModelCall:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentRun:
    agent_name: str
    task: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    status: str = "running"
    tool_calls: list[ToolCall] = field(default_factory=list)
    model_calls: list[ModelCall] = field(default_factory=list)
    thought_log: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def duration_ms(self) -> int:
        if self.ended_at is None:
            return int((datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000)
        return int((self.ended_at - self.started_at).total_seconds() * 1000)

    @property
    def total_tokens(self) -> int:
        return sum(m.input_tokens + m.output_tokens for m in self.model_calls)

    @property
    def total_cost(self) -> float:
        return sum(m.cost_usd for m in self.model_calls)

    def add_thought(self, thought: str):
        self.thought_log.append(thought)

    def add_tool_call(self, tool_name: str, input_summary: str,
                      output_summary: str, duration_ms: int):
        self.tool_calls.append(ToolCall(
            tool_name=tool_name, input_summary=input_summary,
            output_summary=output_summary, duration_ms=duration_ms,
        ))

    def add_model_call(self, model: str, provider: str, input_tokens: int,
                       output_tokens: int, cost_usd: float, duration_ms: int):
        self.model_calls.append(ModelCall(
            model=model, provider=provider, input_tokens=input_tokens,
            output_tokens=output_tokens, cost_usd=cost_usd, duration_ms=duration_ms,
        ))

    def finish(self, status: str = "completed", error: str = ""):
        self.ended_at = datetime.now(timezone.utc)
        self.status = status
        self.error = error

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "task": self.task,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "tool_calls": [
                {
                    "tool": t.tool_name,
                    "input": t.input_summary,
                    "output": t.output_summary,
                    "duration_ms": t.duration_ms,
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in self.tool_calls
            ],
            "model_calls": [
                {
                    "model": m.model,
                    "provider": m.provider,
                    "input_tokens": m.input_tokens,
                    "output_tokens": m.output_tokens,
                    "cost_usd": m.cost_usd,
                    "duration_ms": m.duration_ms,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self.model_calls
            ],
            "thought_log": self.thought_log,
            "error": self.error,
        }


class ObservabilityStore:
    """In-memory store for agent runs. Persisted to SQLite on completion."""

    def __init__(self):
        self._runs: list[AgentRun] = []
        self._active: dict[str, AgentRun] = {}  # agent_name -> current run

    def start_run(self, agent_name: str, task: str) -> AgentRun:
        run = AgentRun(agent_name=agent_name, task=task)
        self._active[agent_name] = run
        return run

    def finish_run(self, agent_name: str, status: str = "completed",
                   error: str = ""):
        run = self._active.pop(agent_name, None)
        if run:
            run.finish(status=status, error=error)
            self._runs.append(run)
        return run

    def get_active(self) -> list[AgentRun]:
        return list(self._active.values())

    def get_recent(self, n: int = 20) -> list[AgentRun]:
        return self._runs[-n:]

    def get_all(self) -> list[AgentRun]:
        return self._runs + list(self._active.values())
