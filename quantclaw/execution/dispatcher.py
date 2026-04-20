"""Dispatches tasks to agents with plan-aware parallel execution."""
from __future__ import annotations
import asyncio
from quantclaw.execution.pool import AgentPool
from quantclaw.execution.plan import Plan, PlanStep, StepStatus
from quantclaw.agents.base import AgentResult, AgentStatus
from quantclaw.events.bus import EventBus
from quantclaw.events.types import Event, EventType

class Dispatcher:
    def __init__(self, pool: AgentPool, bus: EventBus | None = None,
                 cancel_event: asyncio.Event | None = None):
        self._pool = pool
        self._bus = bus
        self._cancel = cancel_event

    async def _emit(self, event_type: EventType, payload: dict) -> None:
        if self._bus:
            await self._bus.publish(Event(
                type=event_type,
                payload=payload,
                source_agent="scheduler",
            ))

    async def dispatch(self, agent_name: str, task: dict) -> AgentResult:
        agent = self._pool.get(agent_name)
        if agent is None:
            import logging
            logging.getLogger(__name__).warning("Dispatch to unknown agent: %s", agent_name)
            return AgentResult(status=AgentStatus.FAILED, error=f"Unknown agent: {agent_name}")
        return await agent.run(task)

    async def dispatch_parallel(self, assignments: list[tuple[str, dict]]) -> list[AgentResult]:
        tasks = [self.dispatch(name, task) for name, task in assignments]
        return await asyncio.gather(*tasks)

    async def execute_plan(self, plan: Plan) -> dict[int, AgentResult]:
        """Execute a plan respecting dependencies and parallelism.

        Steps with no unmet dependencies run in parallel.
        Steps with dependencies wait until their deps complete.
        Skipped steps are ignored.
        Upstream results are injected via ``_upstream_results`` key.
        """
        results: dict[int, AgentResult] = {}

        while not plan.is_complete():
            # Check cancellation before each round
            if self._cancel and self._cancel.is_set():
                for step in plan.steps:
                    if step.status in (StepStatus.APPROVED, StepStatus.PENDING):
                        step.status = StepStatus.SKIPPED
                break

            ready = plan.get_ready_steps()
            if not ready:
                # Check for blocked steps (approved but deps failed)
                blocked = [s for s in plan.steps
                           if s.status in (StepStatus.APPROVED, StepStatus.PENDING)
                           and any(plan.results.get(d) and plan.results[d].status == AgentStatus.FAILED
                                   for d in s.depends_on)]
                if blocked:
                    for s in blocked:
                        s.status = StepStatus.SKIPPED
                    continue  # Try again with blocked steps skipped
                break

            # Broadcast when dispatching multiple steps in parallel
            if len(ready) > 1:
                await self._emit(EventType.ORCHESTRATION_BROADCAST, {
                    "plan_id": plan.id,
                    "targets": [s.agent for s in ready],
                    "step_ids": [s.id for s in ready],
                })

            async def run_step(step: PlanStep) -> tuple[int, AgentResult]:
                if self._cancel and self._cancel.is_set():
                    step.status = StepStatus.SKIPPED
                    return step.id, AgentResult(status=AgentStatus.FAILED, error="Cancelled")

                # Inject upstream results
                upstream = {}
                for dep_id in step.depends_on:
                    if dep_id in results and results[dep_id].status == AgentStatus.SUCCESS:
                        upstream[str(dep_id)] = results[dep_id].data
                task = {**step.task, "_upstream_results": upstream}

                import logging, json as _json
                _logger = logging.getLogger(__name__)
                _logger.info(
                    "Executing step %d: agent=%s, description=%s, upstream_keys=%s",
                    step.id, step.agent, step.description, list(upstream.keys()),
                )
                # Verbose logging — toggle in quantclaw/config/default.yaml: verbose_agent_logging
                if self._pool._config.get("verbose_agent_logging", False):
                    _logger.info("Step %d task: %s", step.id,
                                 _json.dumps(step.task, default=str)[:500])

                await self._emit(EventType.ORCHESTRATION_STEP_STARTED, {
                    "plan_id": plan.id,
                    "step_id": step.id,
                    "agent": step.agent,
                    "description": step.description,
                })

                # Keep the floor/event stream rich, but avoid flooding the chat
                # transcript with step-start boilerplate unless explicitly enabled.
                if self._pool._config.get("orchestration", {}).get("chat_step_starts", False):
                    await self._emit(EventType.CHAT_NARRATIVE, {
                        "message": step.description,
                        "role": step.agent,
                    })

                step.status = StepStatus.RUNNING
                step_timeout = self._pool._config.get("sandbox", {}).get("timeout", 60) * 3  # 3x sandbox timeout
                try:
                    result = await asyncio.wait_for(
                        self.dispatch(step.agent, task),
                        timeout=step_timeout,
                    )
                except asyncio.TimeoutError:
                    result = AgentResult(status=AgentStatus.FAILED, error=f"Step timed out after {step_timeout}s")

                import logging as _log, json as _j
                _log2 = _log.getLogger(__name__)
                _log2.info(
                    "Step %d (%s) finished: status=%s, data_keys=%s, error=%s",
                    step.id, step.agent, result.status,
                    list(result.data.keys()) if result.data else [],
                    result.error[:100] if result.error else "",
                )
                # Verbose logging — shows full result data
                if self._pool._config.get("verbose_agent_logging", False) and result.data:
                    _log2.info("Step %d result data: %s", step.id,
                               _j.dumps(result.data, default=str)[:1000])

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

    async def explore_variants(self, agent_name: str, variants: list[dict]) -> list[AgentResult]:
        """Spawn parallel subagents to explore multiple strategy variants.

        Each variant is a task dict. All run the same agent type in parallel.
        Returns results sorted by quality (if sharpe is in result data).
        """
        results = await self.dispatch_parallel([(agent_name, v) for v in variants])

        # Sort by sharpe if available
        def sort_key(r: AgentResult) -> float:
            if r.status == AgentStatus.FAILED:
                return -999
            return r.data.get("sharpe", r.data.get("score", 0))

        return sorted(results, key=sort_key, reverse=True)
