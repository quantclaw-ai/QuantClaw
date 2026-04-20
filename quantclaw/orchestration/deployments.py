"""Paper deployment registry and allocator for profit campaigns."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib

from quantclaw.agents.base import AgentStatus
from quantclaw.orchestration.playbook import EntryType, Playbook


class DeploymentStatus(StrEnum):
    ACTIVE = "active"
    WATCHLIST = "watchlist"
    RETIRED = "retired"


@dataclass
class PaperDeployment:
    id: str
    campaign_id: str
    strategy_key: str
    strategy_path: str = ""
    status: DeploymentStatus = DeploymentStatus.WATCHLIST
    allocation_pct: float = 0.0
    score: float = 0.0
    sharpe: float = 0.0
    held_out_sharpe: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    paper_runs: int = 0
    last_equity: float = 0.0
    source_cycle: int = 0
    model_type: str = ""
    verdict: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "strategy_key": self.strategy_key,
            "strategy_path": self.strategy_path,
            "status": self.status.value,
            "allocation_pct": self.allocation_pct,
            "score": self.score,
            "sharpe": self.sharpe,
            "held_out_sharpe": self.held_out_sharpe,
            "annual_return": self.annual_return,
            "max_drawdown": self.max_drawdown,
            "paper_runs": self.paper_runs,
            "last_equity": self.last_equity,
            "source_cycle": self.source_cycle,
            "model_type": self.model_type,
            "verdict": self.verdict,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PaperDeployment:
        return cls(
            id=data.get("id", ""),
            campaign_id=data.get("campaign_id", ""),
            strategy_key=data.get("strategy_key", ""),
            strategy_path=data.get("strategy_path", ""),
            status=DeploymentStatus(data.get("status", DeploymentStatus.WATCHLIST.value)),
            allocation_pct=float(data.get("allocation_pct", 0.0)),
            score=float(data.get("score", 0.0)),
            sharpe=float(data.get("sharpe", 0.0)),
            held_out_sharpe=float(data.get("held_out_sharpe", 0.0)),
            annual_return=float(data.get("annual_return", 0.0)),
            max_drawdown=float(data.get("max_drawdown", 0.0)),
            paper_runs=int(data.get("paper_runs", 0)),
            last_equity=float(data.get("last_equity", 0.0)),
            source_cycle=int(data.get("source_cycle", 0)),
            model_type=data.get("model_type", ""),
            verdict=data.get("verdict", ""),
            updated_at=data.get("updated_at", ""),
        )

    def prompt_summary(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "allocation_pct": round(self.allocation_pct, 3),
            "score": round(self.score, 3),
            "sharpe": round(self.sharpe, 3),
            "held_out_sharpe": round(self.held_out_sharpe, 3),
            "paper_runs": self.paper_runs,
            "model_type": self.model_type,
            "strategy_path": self.strategy_path,
        }


@dataclass
class AllocationUpdate:
    message: str = ""
    active_count: int = 0
    watchlist_count: int = 0


class DeploymentAllocator:
    """Manage a paper-trading portfolio of validated strategy candidates."""

    def __init__(self, playbook: Playbook, config: dict):
        self._playbook = playbook
        self._config = config

    async def restore(self, campaign_id: str) -> list[PaperDeployment]:
        entries = await self._playbook.query(entry_type=EntryType.DEPLOYMENT_STATE)
        latest: dict[str, PaperDeployment] = {}
        for entry in entries:
            try:
                deployment = PaperDeployment.from_dict(entry.content)
            except Exception:
                continue
            if deployment.campaign_id != campaign_id:
                continue
            latest[deployment.id] = deployment
        return list(latest.values())

    async def prompt_context(self, campaign_id: str) -> dict:
        deployments = await self.restore(campaign_id)
        active = [d for d in deployments if d.status == DeploymentStatus.ACTIVE]
        watchlist = [d for d in deployments if d.status == DeploymentStatus.WATCHLIST]
        active.sort(key=lambda item: item.score, reverse=True)
        watchlist.sort(key=lambda item: item.score, reverse=True)
        return {
            "active_slots": self._max_active(),
            "active_count": len(active),
            "watchlist_count": len(watchlist),
            "active_deployments": [d.prompt_summary() for d in active[: self._max_active()]],
            "watchlist": [d.prompt_summary() for d in watchlist[: self._watchlist_size()]],
        }

    async def rebalance(
        self,
        campaign_id: str,
        cycle_number: int,
        results: dict,
        evaluation: dict | None,
    ) -> AllocationUpdate | None:
        deployments = await self.restore(campaign_id)
        existing = {deployment.id: deployment for deployment in deployments}
        candidate = self._extract_candidate(campaign_id, cycle_number, results, evaluation)
        if candidate:
            incumbent = existing.get(candidate.id)
            if incumbent:
                candidate.paper_runs = max(candidate.paper_runs, incumbent.paper_runs)
                candidate.last_equity = max(candidate.last_equity, incumbent.last_equity)
            existing[candidate.id] = candidate

        if not existing:
            return None

        self._apply_paper_updates(existing, results)
        ordered = sorted(existing.values(), key=lambda item: item.score, reverse=True)
        self._assign_statuses(ordered)

        for deployment in ordered:
            deployment.updated_at = datetime.now(timezone.utc).isoformat()
            await self._playbook.add(
                EntryType.DEPLOYMENT_STATE,
                deployment.to_dict(),
                tags=["deployment", deployment.status.value, campaign_id],
            )

        active = [deployment for deployment in ordered if deployment.status == DeploymentStatus.ACTIVE]
        watchlist = [deployment for deployment in ordered if deployment.status == DeploymentStatus.WATCHLIST]
        summary = self._summary(active, watchlist)
        await self._playbook.add(
            EntryType.ALLOCATION_DECISION,
            {
                "campaign_id": campaign_id,
                "cycle": cycle_number,
                "active_ids": [deployment.id for deployment in active],
                "watchlist_ids": [deployment.id for deployment in watchlist],
                "summary": summary,
            },
            tags=["allocator", campaign_id],
        )
        return AllocationUpdate(
            message=summary,
            active_count=len(active),
            watchlist_count=len(watchlist),
        )

    def _extract_candidate(
        self,
        campaign_id: str,
        cycle_number: int,
        results: dict,
        evaluation: dict | None,
    ) -> PaperDeployment | None:
        aggregate: dict[str, object] = {}
        paper_data: dict | None = None
        for result in results.values():
            if result.status != AgentStatus.SUCCESS:
                continue
            data = result.data or {}
            if "strategy_path" in data and not aggregate.get("strategy_path"):
                aggregate["strategy_path"] = data["strategy_path"]
            if "model_type" in data and not aggregate.get("model_type"):
                aggregate["model_type"] = data["model_type"]
            if "verdict" in data:
                aggregate["verdict"] = data["verdict"]
            for key in ("sharpe", "annual_return", "max_drawdown", "held_out_sharpe"):
                if key in data:
                    aggregate[key] = data[key]
            if data.get("mode") == "paper":
                paper_data = data

        verdict = str(aggregate.get("verdict", evaluation.get("verdict", "") if evaluation else ""))
        held_out = self._to_float(aggregate.get("held_out_sharpe", 0.0))
        sharpe = self._to_float(aggregate.get("sharpe", 0.0))
        if not self._qualifies(verdict, held_out, sharpe):
            return None

        strategy_path = str(aggregate.get("strategy_path", ""))
        strategy_key = strategy_path or f"{aggregate.get('model_type', 'candidate')}:{cycle_number}"
        deployment_id = self._make_id(campaign_id, strategy_key)
        return PaperDeployment(
            id=deployment_id,
            campaign_id=campaign_id,
            strategy_key=strategy_key,
            strategy_path=strategy_path,
            score=self._score(
                sharpe=sharpe,
                held_out_sharpe=held_out,
                annual_return=self._to_float(aggregate.get("annual_return", 0.0)),
                max_drawdown=self._to_float(aggregate.get("max_drawdown", 0.0)),
            ),
            sharpe=sharpe,
            held_out_sharpe=held_out,
            annual_return=self._to_float(aggregate.get("annual_return", 0.0)),
            max_drawdown=self._to_float(aggregate.get("max_drawdown", 0.0)),
            paper_runs=1 if paper_data else 0,
            last_equity=self._extract_equity(paper_data),
            source_cycle=cycle_number,
            model_type=str(aggregate.get("model_type", "")),
            verdict=verdict,
        )

    def _apply_paper_updates(self, deployments: dict[str, PaperDeployment], results: dict) -> None:
        for result in results.values():
            if result.status != AgentStatus.SUCCESS:
                continue
            data = result.data or {}
            if data.get("mode") != "paper":
                continue
            strategy_path = data.get("strategy_path", "")
            if not strategy_path:
                continue
            for deployment in deployments.values():
                if deployment.strategy_path and deployment.strategy_path == strategy_path:
                    deployment.paper_runs += 1
                    deployment.last_equity = max(
                        deployment.last_equity,
                        self._extract_equity(data),
                    )

    def _assign_statuses(self, ordered: list[PaperDeployment]) -> None:
        active_scores = [max(deployment.score, 0.01) for deployment in ordered[: self._max_active()]]
        total_active_score = sum(active_scores) or 1.0
        for index, deployment in enumerate(ordered):
            if index < self._max_active():
                deployment.status = DeploymentStatus.ACTIVE
                deployment.allocation_pct = active_scores[index] / total_active_score
            elif index < self._max_active() + self._watchlist_size():
                deployment.status = DeploymentStatus.WATCHLIST
                deployment.allocation_pct = 0.0
            else:
                deployment.status = DeploymentStatus.RETIRED
                deployment.allocation_pct = 0.0

    def _qualifies(self, verdict: str, held_out: float, sharpe: float) -> bool:
        if verdict == "validated":
            return True
        if held_out >= self._min_held_out():
            return True
        return held_out >= self._watchlist_min_held_out()

    def _score(
        self,
        *,
        sharpe: float,
        held_out_sharpe: float,
        annual_return: float,
        max_drawdown: float,
    ) -> float:
        return (
            held_out_sharpe * 0.6
            + sharpe * 0.25
            + annual_return * 0.15 * 10
            - abs(max_drawdown) * 0.2 * 10
        )

    def _summary(
        self,
        active: list[PaperDeployment],
        watchlist: list[PaperDeployment],
    ) -> str:
        if not active and not watchlist:
            return ""
        active_labels = ", ".join(
            f"{self._display_name(deployment)} ({deployment.allocation_pct:.0%})"
            for deployment in active
        ) or "none"
        watch_labels = ", ".join(
            self._display_name(deployment) for deployment in watchlist
        ) or "none"
        return (
            "Allocator update: "
            f"{len(active)} active paper deployment{'s' if len(active) != 1 else ''} "
            f"and {len(watchlist)} watchlist candidate{'s' if len(watchlist) != 1 else ''}. "
            f"Active: {active_labels}. Watchlist: {watch_labels}."
        )

    @staticmethod
    def _display_name(deployment: PaperDeployment) -> str:
        if deployment.strategy_path:
            from pathlib import Path

            stem = Path(deployment.strategy_path).stem
            if stem:
                return stem
        if deployment.model_type:
            return f"{deployment.model_type}:{deployment.id[:4]}"
        return deployment.id

    def _max_active(self) -> int:
        return int(self._config.get("campaigns", {}).get("max_active_paper_deployments", 2))

    def _watchlist_size(self) -> int:
        return int(self._config.get("campaigns", {}).get("paper_watchlist_size", 3))

    def _min_held_out(self) -> float:
        return float(self._config.get("campaigns", {}).get("validation_promote_held_out_sharpe", 0.25))

    def _min_sharpe(self) -> float:
        return float(self._config.get("campaigns", {}).get("paper_candidate_min_sharpe", 1.0))

    def _watchlist_min_held_out(self) -> float:
        return float(
            self._config.get("campaigns", {}).get(
                "paper_watchlist_min_held_out_sharpe", 0.15
            )
        )

    @staticmethod
    def _make_id(campaign_id: str, strategy_key: str) -> str:
        digest = hashlib.sha1(f"{campaign_id}:{strategy_key}".encode("utf-8")).hexdigest()
        return digest[:12]

    @staticmethod
    def _extract_equity(data: dict | None) -> float:
        if not data:
            return 0.0
        portfolio = data.get("portfolio", {})
        try:
            return float(portfolio.get("equity", 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
