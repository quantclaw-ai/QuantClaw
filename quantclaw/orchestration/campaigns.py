"""Persistent profit-campaign scaffolding above the OODA loop."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import uuid

from quantclaw.agents.base import AgentStatus
from quantclaw.orchestration.playbook import EntryType, Playbook


DEFAULT_BROAD_GOAL_PATTERNS = (
    "make money",
    "make me cash",
    "go make money",
    "go make me cash",
    "find profitable",
    "profitable strategies",
    "find alpha",
    "find strategies",
    "compound capital",
    "grow capital",
)


class CampaignPhase(StrEnum):
    DISCOVER = "discover"
    VALIDATE = "validate"
    PAPER = "paper"
    REFINE = "refine"


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass
class ProfitCampaign:
    id: str
    root_goal: str
    status: CampaignStatus = CampaignStatus.ACTIVE
    phase: CampaignPhase = CampaignPhase.DISCOVER
    total_cycles: int = 0
    phase_cycles: int = 0
    consecutive_failures: int = 0
    validated_candidates: int = 0
    paper_deployments: int = 0
    best_sharpe: float = 0.0
    best_held_out_sharpe: float = 0.0
    last_subgoal: str = ""
    last_verdict: str = ""
    last_reasoning: str = ""
    last_checkpoint_cycle: int = 0
    last_improvement_cycle: int = 0
    resume_cycle: int = 0
    stop_reason: str = ""
    paper_only: bool = True
    # Paper-phase health tracking (steady-state operation, not search).
    consecutive_paper_no_execute: int = 0
    worst_paper_drawdown: float = 0.0  # most-negative observed; 0 = no drawdown yet

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "root_goal": self.root_goal,
            "status": self.status.value,
            "phase": self.phase.value,
            "total_cycles": self.total_cycles,
            "phase_cycles": self.phase_cycles,
            "consecutive_failures": self.consecutive_failures,
            "validated_candidates": self.validated_candidates,
            "paper_deployments": self.paper_deployments,
            "best_sharpe": self.best_sharpe,
            "best_held_out_sharpe": self.best_held_out_sharpe,
            "last_subgoal": self.last_subgoal,
            "last_verdict": self.last_verdict,
            "last_reasoning": self.last_reasoning,
            "last_checkpoint_cycle": self.last_checkpoint_cycle,
            "last_improvement_cycle": self.last_improvement_cycle,
            "resume_cycle": self.resume_cycle,
            "stop_reason": self.stop_reason,
            "paper_only": self.paper_only,
            "consecutive_paper_no_execute": self.consecutive_paper_no_execute,
            "worst_paper_drawdown": self.worst_paper_drawdown,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProfitCampaign:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            root_goal=data.get("root_goal", ""),
            status=CampaignStatus(data.get("status", CampaignStatus.ACTIVE.value)),
            phase=CampaignPhase(data.get("phase", CampaignPhase.DISCOVER.value)),
            total_cycles=int(data.get("total_cycles", 0)),
            phase_cycles=int(data.get("phase_cycles", 0)),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            validated_candidates=int(data.get("validated_candidates", 0)),
            paper_deployments=int(data.get("paper_deployments", 0)),
            best_sharpe=float(data.get("best_sharpe", 0.0)),
            best_held_out_sharpe=float(data.get("best_held_out_sharpe", 0.0)),
            last_subgoal=data.get("last_subgoal", ""),
            last_verdict=data.get("last_verdict", ""),
            last_reasoning=data.get("last_reasoning", ""),
            last_checkpoint_cycle=int(data.get("last_checkpoint_cycle", 0)),
            last_improvement_cycle=int(data.get("last_improvement_cycle", 0)),
            resume_cycle=int(data.get("resume_cycle", 0)),
            stop_reason=data.get("stop_reason", ""),
            paper_only=bool(data.get("paper_only", True)),
            consecutive_paper_no_execute=int(data.get("consecutive_paper_no_execute", 0)),
            worst_paper_drawdown=float(data.get("worst_paper_drawdown", 0.0)),
        )

    def to_prompt_context(self) -> dict:
        return {
            "campaign_id": self.id,
            "root_goal": self.root_goal,
            "status": self.status.value,
            "phase": self.phase.value,
            "total_cycles": self.total_cycles,
            "phase_cycles": self.phase_cycles,
            "validated_candidates": self.validated_candidates,
            "paper_deployments": self.paper_deployments,
            "best_sharpe": self.best_sharpe,
            "best_held_out_sharpe": self.best_held_out_sharpe,
            "paper_only": self.paper_only,
            "last_verdict": self.last_verdict,
            "stop_reason": self.stop_reason,
        }


@dataclass
class CampaignUpdate:
    transition_message: str = ""
    checkpoint_message: str = ""
    status_message: str = ""


class CampaignManager:
    """Compile broad goals into a long-lived exploration campaign."""

    def __init__(self, playbook: Playbook, config: dict):
        self._playbook = playbook
        self._config = config

    def matches(self, goal: str) -> bool:
        lower = goal.lower().strip()
        patterns = self._config.get("campaigns", {}).get(
            "broad_goal_patterns", list(DEFAULT_BROAD_GOAL_PATTERNS)
        )
        return any(pattern.lower() in lower for pattern in patterns)

    def activate(self, goal: str, existing: ProfitCampaign | None = None) -> ProfitCampaign | None:
        if not self.matches(goal):
            return None
        if existing and existing.root_goal.strip().lower() == goal.strip().lower():
            if existing.status != CampaignStatus.ACTIVE:
                existing.resume_cycle = existing.total_cycles
                existing.phase_cycles = 0
            existing.status = CampaignStatus.ACTIVE
            existing.stop_reason = ""
            return existing
        return ProfitCampaign(id=str(uuid.uuid4())[:8], root_goal=goal)

    async def restore(self, goal_hint: str = "") -> ProfitCampaign | None:
        entries = await self._playbook.query(entry_type=EntryType.CAMPAIGN_STATE)
        normalized_hint = goal_hint.strip().lower()
        for entry in reversed(entries):
            try:
                campaign = ProfitCampaign.from_dict(entry.content)
            except Exception:
                continue
            if normalized_hint and campaign.root_goal.strip().lower() != normalized_hint:
                continue
            if campaign.status == CampaignStatus.ACTIVE:
                return campaign
        if goal_hint:
            return self.activate(goal_hint)
        return None

    async def persist(self, campaign: ProfitCampaign) -> None:
        await self._playbook.add(
            EntryType.CAMPAIGN_STATE,
            campaign.to_dict(),
            tags=["campaign", campaign.phase.value, campaign.status.value],
        )

    def next_subgoal(self, campaign: ProfitCampaign, deployments: dict | None = None) -> str:
        self._promote_for_progress(campaign)
        deployment_note = ""
        if deployments:
            active = deployments.get("active_count", 0)
            watchlist = deployments.get("watchlist_count", 0)
            if active or watchlist:
                deployment_note = (
                    f" Current paper portfolio: {active} active deployment"
                    f"{'s' if active != 1 else ''}, {watchlist} watchlist candidate"
                    f"{'s' if watchlist != 1 else ''}."
                )
        if campaign.phase == CampaignPhase.DISCOVER:
            subgoal = (
                f"Campaign objective: {campaign.root_goal}. "
                "Explore for profitable trading strategies across materially different factor families, "
                "universes, and model types. Favor breadth and novelty, then backtest the strongest "
                "candidates and report concrete metrics. Paper trade only after validation."
                f"{deployment_note}"
            )
        elif campaign.phase == CampaignPhase.VALIDATE:
            subgoal = (
                f"Campaign objective: {campaign.root_goal}. "
                "Take the strongest candidate strategies, run stricter backtests plus held-out evaluation, "
                "reject overfit ideas, and nominate one candidate worthy of paper trading. "
                "Prefer statistical validity over flashy in-sample Sharpe."
                f"{deployment_note}"
            )
        elif campaign.phase == CampaignPhase.PAPER:
            subgoal = (
                f"Campaign objective: {campaign.root_goal}. "
                "Manage the paper deployment portfolio: add the strongest validated candidate if it beats incumbents, "
                "keep only the highest-conviction paper strategies active, and retire weak ones. "
                "Run compliance and risk checks first, compare paper behavior with backtest expectations, "
                "and decide whether to keep, refine, or retire the strategy."
                f"{deployment_note}"
            )
        else:
            subgoal = (
                f"Campaign objective: {campaign.root_goal}. "
                "The current search path is stalling. Switch to a materially different hypothesis family, "
                "market regime thesis, or model class, then restart discovery with fresh candidates. "
                "Avoid repeating prior factors and models."
                f"{deployment_note}"
            )
        campaign.last_subgoal = subgoal
        return subgoal

    async def record_cycle(
        self,
        campaign: ProfitCampaign,
        results: dict,
        evaluation: dict | None,
    ) -> CampaignUpdate:
        update = CampaignUpdate()
        metrics = self._extract_metrics(results)
        previous_best_sharpe = campaign.best_sharpe
        previous_best_held_out = campaign.best_held_out_sharpe
        campaign.total_cycles += 1
        campaign.phase_cycles += 1
        campaign.best_sharpe = max(campaign.best_sharpe, metrics["best_sharpe"])
        campaign.best_held_out_sharpe = max(
            campaign.best_held_out_sharpe, metrics["best_held_out_sharpe"]
        )
        if (
            campaign.best_sharpe >= previous_best_sharpe + self._min_improvement_delta()
            or campaign.best_held_out_sharpe >= previous_best_held_out + self._min_improvement_delta()
        ):
            campaign.last_improvement_cycle = campaign.total_cycles
        if metrics["validated"]:
            campaign.validated_candidates += 1
        if metrics["paper_executed"]:
            campaign.paper_deployments += 1

        # Paper-phase health tracking. Counter resets on a successful paper
        # execute; increments on cycles where paper failed to run any orders.
        # Outside paper phase the counter is dormant (reset on transition).
        if campaign.phase == CampaignPhase.PAPER:
            if metrics["paper_executed"]:
                campaign.consecutive_paper_no_execute = 0
            else:
                campaign.consecutive_paper_no_execute += 1
            # Track worst drawdown ever observed during paper.
            campaign.worst_paper_drawdown = min(
                campaign.worst_paper_drawdown, metrics["worst_drawdown"]
            )

        verdict = (evaluation or {}).get("verdict", "")
        campaign.last_verdict = verdict
        campaign.last_reasoning = (evaluation or {}).get("reasoning", "")

        if verdict == "abandon":
            campaign.consecutive_failures += 1
        elif verdict == "pursue":
            campaign.consecutive_failures = 0

        phase_before = campaign.phase
        if campaign.phase in (CampaignPhase.DISCOVER, CampaignPhase.VALIDATE):
            if metrics["validated"] or campaign.best_held_out_sharpe >= self._validate_threshold():
                campaign.phase = CampaignPhase.PAPER
            elif (
                campaign.phase == CampaignPhase.DISCOVER
                and campaign.phase_cycles >= self._min_discovery_cycles()
                and campaign.best_sharpe >= self._discover_threshold()
            ):
                campaign.phase = CampaignPhase.VALIDATE
            elif campaign.consecutive_failures >= self._max_consecutive_failures():
                campaign.phase = CampaignPhase.REFINE
        elif campaign.phase == CampaignPhase.PAPER:
            if campaign.consecutive_failures >= self._max_consecutive_failures():
                campaign.phase = CampaignPhase.REFINE
        elif campaign.phase == CampaignPhase.REFINE and verdict in ("iterate", "pursue"):
            campaign.phase = CampaignPhase.DISCOVER

        if campaign.phase != phase_before:
            campaign.phase_cycles = 0
            # Each new phase starts with a clean improvement clock — search
            # phases shouldn't inherit "stagnation" from earlier phases, and
            # paper-only counters reset cleanly on entry/exit.
            campaign.last_improvement_cycle = campaign.total_cycles
            campaign.consecutive_paper_no_execute = 0
            if campaign.phase != CampaignPhase.PAPER:
                campaign.worst_paper_drawdown = 0.0
            update.transition_message = self._transition_message(
                phase_before, campaign.phase, campaign
            )

        status_message = self._apply_stop_conditions(campaign)
        if status_message:
            update.status_message = status_message

        if self.should_checkpoint(campaign):
            campaign.last_checkpoint_cycle = campaign.total_cycles
            update.checkpoint_message = self.progress_summary(campaign)

        await self.persist(campaign)
        return update

    def should_checkpoint(self, campaign: ProfitCampaign) -> bool:
        every = int(self._config.get("campaigns", {}).get("checkpoint_every_cycles", 3))
        if every <= 0 or campaign.total_cycles <= 0:
            return False
        return (
            campaign.total_cycles % every == 0
            and campaign.last_checkpoint_cycle != campaign.total_cycles
        )

    def progress_summary(self, campaign: ProfitCampaign) -> str:
        return (
            "Profit campaign checkpoint: "
            f"{campaign.total_cycles} cycle{'s' if campaign.total_cycles != 1 else ''}, "
            f"phase={campaign.phase.value}, status={campaign.status.value}, "
            f"best_sharpe={campaign.best_sharpe:.2f}, "
            f"best_held_out={campaign.best_held_out_sharpe:.2f}, "
            f"validated={campaign.validated_candidates}, "
            f"paper_runs={campaign.paper_deployments}. "
            f"Next focus: {campaign.last_subgoal or self.next_subgoal(campaign)}"
        )

    def _promote_for_progress(self, campaign: ProfitCampaign) -> None:
        if (
            campaign.phase == CampaignPhase.DISCOVER
            and campaign.phase_cycles >= self._min_discovery_cycles()
            and campaign.best_sharpe >= self._discover_threshold()
        ):
            campaign.phase = CampaignPhase.VALIDATE
            campaign.phase_cycles = 0
        elif (
            campaign.phase in (CampaignPhase.DISCOVER, CampaignPhase.VALIDATE)
            and campaign.best_held_out_sharpe >= self._validate_threshold()
        ):
            campaign.phase = CampaignPhase.PAPER
            campaign.phase_cycles = 0
        elif campaign.consecutive_failures >= self._max_consecutive_failures():
            campaign.phase = CampaignPhase.REFINE
            campaign.phase_cycles = 0

    def _extract_metrics(self, results: dict) -> dict:
        best_sharpe = 0.0
        best_held_out_sharpe = 0.0
        worst_drawdown = 0.0   # most-negative observed
        validated = False
        paper_executed = False

        for result in results.values():
            if result.status != AgentStatus.SUCCESS:
                continue
            data = result.data or {}
            best_sharpe = max(best_sharpe, self._to_float(data.get("sharpe", 0.0)))
            best_held_out_sharpe = max(
                best_held_out_sharpe, self._to_float(data.get("held_out_sharpe", 0.0))
            )
            dd = self._to_float(data.get("max_drawdown", 0.0))
            if dd < worst_drawdown:
                worst_drawdown = dd
            if data.get("verdict") == "validated":
                validated = True
            if data.get("mode") == "paper":
                paper_executed = True

        return {
            "best_sharpe": best_sharpe,
            "best_held_out_sharpe": best_held_out_sharpe,
            "worst_drawdown": worst_drawdown,
            "validated": validated,
            "paper_executed": paper_executed,
        }

    def _discover_threshold(self) -> float:
        return float(
            self._config.get("campaigns", {}).get("discovery_promote_sharpe", 0.75)
        )

    def _validate_threshold(self) -> float:
        return float(
            self._config.get("campaigns", {}).get(
                "validation_promote_held_out_sharpe", 0.25
            )
        )

    def _min_discovery_cycles(self) -> int:
        return int(self._config.get("campaigns", {}).get("min_discovery_cycles", 2))

    def _max_consecutive_failures(self) -> int:
        return int(self._config.get("campaigns", {}).get("max_consecutive_failures", 2))

    def _max_total_cycles(self) -> int:
        return int(self._config.get("campaigns", {}).get("max_total_cycles", 12))

    def _max_stagnant_cycles(self) -> int:
        return int(self._config.get("campaigns", {}).get("max_stagnant_cycles", 6))

    def _max_refine_cycles(self) -> int:
        return int(self._config.get("campaigns", {}).get("max_refine_cycles", 3))

    def _min_improvement_delta(self) -> float:
        return float(self._config.get("campaigns", {}).get("min_improvement_delta", 0.05))

    def _apply_stop_conditions(self, campaign: ProfitCampaign) -> str:
        if campaign.status != CampaignStatus.ACTIVE:
            return ""

        max_total_cycles = self._max_total_cycles()
        cycles_since_resume = campaign.total_cycles - campaign.resume_cycle
        if max_total_cycles > 0 and cycles_since_resume >= max_total_cycles:
            campaign.status = CampaignStatus.PAUSED
            campaign.stop_reason = f"Reached max_total_cycles={max_total_cycles}"
            return (
                f"Profit campaign paused after {cycles_since_resume} cycle"
                f"{'s' if cycles_since_resume != 1 else ''} since resume "
                f"(threshold {max_total_cycles}). Re-run the goal to resume."
            )

        max_refine_cycles = self._max_refine_cycles()
        if (
            max_refine_cycles > 0
            and campaign.phase == CampaignPhase.REFINE
            and campaign.phase_cycles >= max_refine_cycles
        ):
            campaign.status = CampaignStatus.PAUSED
            campaign.stop_reason = (
                f"Reached max_refine_cycles={max_refine_cycles} in refine phase"
            )
            return (
                "Profit campaign paused because the refine phase kept stalling. "
                "Re-run the goal to resume with a fresh search path."
            )

        # Paper phase is steady-state operation, not search. Stop only on
        # genuine health signals: drawdown breach or repeated execution failure.
        if campaign.phase == CampaignPhase.PAPER:
            dd_limit = abs(self._risk_max_drawdown())
            if dd_limit > 0 and abs(campaign.worst_paper_drawdown) >= dd_limit:
                campaign.status = CampaignStatus.PAUSED
                campaign.stop_reason = (
                    f"Paper drawdown {campaign.worst_paper_drawdown:.2%} breached "
                    f"limit -{dd_limit:.0%}"
                )
                return (
                    f"Profit campaign paused: paper drawdown "
                    f"{campaign.worst_paper_drawdown:.2%} exceeded the configured "
                    f"limit (-{dd_limit:.0%}). Investigate the active strategy "
                    "or re-run the goal to resume after addressing risk."
                )

            max_paper_failures = self._max_consecutive_paper_failures()
            if (
                max_paper_failures > 0
                and campaign.consecutive_paper_no_execute >= max_paper_failures
            ):
                campaign.status = CampaignStatus.PAUSED
                campaign.stop_reason = (
                    f"Paper executor failed to run {campaign.consecutive_paper_no_execute} cycles in a row"
                )
                return (
                    "Profit campaign paused: the paper executor produced no orders "
                    f"for {campaign.consecutive_paper_no_execute} consecutive cycles. "
                    "Check broker connectivity and signal freshness."
                )
            # Paper deliberately ignores stagnation — flat Sharpe is expected.
            return ""

        # Search phases (discover/validate/refine): stagnation IS a real signal.
        max_stagnant_cycles = self._max_stagnant_cycles()
        if max_stagnant_cycles > 0:
            baseline = max(campaign.last_improvement_cycle, campaign.resume_cycle)
            stagnant_cycles = campaign.total_cycles - baseline
            if cycles_since_resume >= max_stagnant_cycles and stagnant_cycles >= max_stagnant_cycles:
                campaign.status = CampaignStatus.PAUSED
                campaign.stop_reason = (
                    f"No material improvement for {stagnant_cycles} cycles"
                )
                return (
                    f"Profit campaign paused after {stagnant_cycles} stagnant cycles without "
                    "material improvement. Re-run the goal to resume."
                )

        return ""

    def _risk_max_drawdown(self) -> float:
        return float(self._config.get("risk", {}).get("max_drawdown", -0.10))

    def _max_consecutive_paper_failures(self) -> int:
        return int(
            self._config.get("campaigns", {}).get("max_consecutive_paper_failures", 5)
        )

    @staticmethod
    def _transition_message(
        old_phase: CampaignPhase,
        new_phase: CampaignPhase,
        campaign: ProfitCampaign,
    ) -> str:
        if old_phase == new_phase:
            return ""
        return (
            "Profit campaign phase shift: "
            f"{old_phase.value} -> {new_phase.value}. "
            f"Best Sharpe so far {campaign.best_sharpe:.2f}, "
            f"best held-out {campaign.best_held_out_sharpe:.2f}."
        )

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
