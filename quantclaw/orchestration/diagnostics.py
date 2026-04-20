"""Anomaly detection for diagnostic feedback loop."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class AnomalyFlag:
    """Single detected anomaly with severity and context."""
    name: str
    severity: str  # "critical", "high", "medium", "low"
    description: str
    context: dict


class AnomalyDetector:
    """Detects problems that should trigger diagnostic agent investigation."""

    @staticmethod
    def detect_validation_anomalies(
        evaluation: dict,
        prior_sharpe: Optional[float] = None,
    ) -> list[AnomalyFlag]:
        """Detect suspicious validation metrics."""
        anomalies = []

        best_result = evaluation.get("best_result", {})
        test_sharpe = best_result.get("sharpe", 0)
        held_out_sharpe = best_result.get("held_out_sharpe", test_sharpe)
        overfit_ratio = best_result.get("overfit_ratio", 1.0)

        # Held-out beats in-sample (backwards from normal overfitting)
        if held_out_sharpe > test_sharpe and test_sharpe > 0:
            ratio = held_out_sharpe / test_sharpe
            if ratio > 1.3:
                anomalies.append(AnomalyFlag(
                    name="held_out_outperforms_insample",
                    severity="high",
                    description=f"Held-out Sharpe ({held_out_sharpe:.2f}) is {ratio:.1%} of in-sample ({test_sharpe:.2f}) — suggests data leakage or validation issue",
                    context={
                        "test_sharpe": test_sharpe,
                        "held_out_sharpe": held_out_sharpe,
                        "ratio": ratio,
                    }
                ))

        # Metric degradation across iterations
        if prior_sharpe and test_sharpe < prior_sharpe * 0.75:
            degradation = (prior_sharpe - test_sharpe) / prior_sharpe
            anomalies.append(AnomalyFlag(
                name="metric_degradation",
                severity="high",
                description=f"Sharpe degraded {degradation:.1%} from {prior_sharpe:.2f} to {test_sharpe:.2f}",
                context={
                    "prior_sharpe": prior_sharpe,
                    "current_sharpe": test_sharpe,
                    "degradation_pct": degradation * 100,
                }
            ))

        # Held-out Sharpe too low
        if held_out_sharpe < 0.5 and held_out_sharpe > 0:
            anomalies.append(AnomalyFlag(
                name="weak_held_out_signal",
                severity="medium",
                description=f"Held-out Sharpe {held_out_sharpe:.2f} is below minimum threshold 0.5 — signal too weak",
                context={"held_out_sharpe": held_out_sharpe}
            ))

        # Excessive overfitting
        if overfit_ratio > 1.25:
            anomalies.append(AnomalyFlag(
                name="excessive_overfitting",
                severity="high",
                description=f"Overfit ratio {overfit_ratio:.2f} exceeds threshold 1.25 — model too specific to training data",
                context={"overfit_ratio": overfit_ratio}
            ))

        return anomalies

    @staticmethod
    def detect_execution_anomalies(summary: dict) -> list[AnomalyFlag]:
        """Detect execution/deployment problems."""
        anomalies = []

        paper = summary.get("paper", {})
        orders_executed = paper.get("orders_executed", 0)
        successful_deployments = paper.get("successful_deployments", 0)
        failed_deployments = paper.get("failed_deployments", 0)

        # Zero orders despite valid allocations
        if orders_executed == 0 and successful_deployments > 0:
            anomalies.append(AnomalyFlag(
                name="zero_orders_with_allocations",
                severity="critical",
                description=f"{successful_deployments} active deployment(s) but 0 orders executed — rebalancing logic broken or portfolio already aligned",
                context={
                    "successful_deployments": successful_deployments,
                    "orders_executed": orders_executed,
                    "failed_deployments": failed_deployments,
                }
            ))

        # All deployments failed
        if failed_deployments > 0 and successful_deployments == 0:
            anomalies.append(AnomalyFlag(
                name="all_deployments_failed",
                severity="critical",
                description=f"All {failed_deployments} deployment(s) failed — likely model loading or data issue",
                context={
                    "failed_deployments": failed_deployments,
                    "successful_deployments": successful_deployments,
                }
            ))

        return anomalies

    @staticmethod
    def detect_portfolio_anomalies(
        campaign: Optional[dict] = None,
        prior_state: Optional[dict] = None,
    ) -> list[AnomalyFlag]:
        """Detect portfolio/allocation problems."""
        anomalies = []

        if not campaign:
            return anomalies

        watchlist = campaign.get("watchlist_candidates", [])
        active = campaign.get("active_deployments", [])
        cycles_since_update = campaign.get("cycles_since_last_allocation_change", 0)

        # Watchlist stagnation (candidates never promoted)
        if len(watchlist) > 0 and cycles_since_update > 50:
            best_candidate = watchlist[0] if watchlist else None
            best_candidate_sharpe = best_candidate.get("held_out_sharpe", 0) if best_candidate else 0
            active_sharpe = max([s.get("held_out_sharpe", 0) for s in active], default=0)

            if best_candidate_sharpe > active_sharpe * 1.2:
                anomalies.append(AnomalyFlag(
                    name="stalled_watchlist_promotion",
                    severity="high",
                    description=f"Top candidate ({best_candidate_sharpe:.2f}) beats incumbent ({active_sharpe:.2f}) by 20% for {cycles_since_update} cycles but not promoted",
                    context={
                        "watchlist_size": len(watchlist),
                        "cycles_stalled": cycles_since_update,
                        "candidate_sharpe": best_candidate_sharpe,
                        "incumbent_sharpe": active_sharpe,
                        "gap_ratio": best_candidate_sharpe / (active_sharpe + 0.01),
                    }
                ))

        # Portfolio composition unchanged
        allocation_changes = campaign.get("allocation_changes_count", 0)
        if allocation_changes == 0 and cycles_since_update > 20:
            anomalies.append(AnomalyFlag(
                name="portfolio_stagnation",
                severity="medium",
                description=f"Portfolio composition unchanged for {cycles_since_update} cycles — no learning or adaptation",
                context={
                    "cycles_without_change": cycles_since_update,
                    "allocation_changes": allocation_changes,
                }
            ))

        # Best Sharpe plateau (no improvement for many cycles)
        best_sharpe_history = campaign.get("best_sharpe_history", [])
        if len(best_sharpe_history) > 20:
            recent_best = max(best_sharpe_history[-20:])
            all_time_best = max(best_sharpe_history)
            if abs(recent_best - all_time_best) < 0.05:
                anomalies.append(AnomalyFlag(
                    name="sharpe_plateau",
                    severity="medium",
                    description=f"Best Sharpe plateaued at {recent_best:.2f} for 20+ cycles — hitting limitations or overfitting",
                    context={
                        "recent_best": recent_best,
                        "all_time_best": all_time_best,
                        "stalled_cycles": 20,
                    }
                ))

        return anomalies

    @staticmethod
    def get_top_anomalies(
        all_anomalies: list[AnomalyFlag],
        max_count: int = 3,
    ) -> list[AnomalyFlag]:
        """Rank and return top N anomalies by severity."""
        severity_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        sorted_anomalies = sorted(
            all_anomalies,
            key=lambda a: severity_rank.get(a.severity, 0),
            reverse=True,
        )
        return sorted_anomalies[:max_count]
