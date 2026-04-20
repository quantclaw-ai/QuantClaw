"""Tests for enriched iteration context in OODA loop."""
import pytest
from quantclaw.agents.base import AgentResult, AgentStatus


def test_iteration_context_extracts_factors():
    """Verify that factor names and metrics are collected from results."""
    results = {
        0: AgentResult(status=AgentStatus.SUCCESS, data={"total_calls": 0}),
        1: AgentResult(status=AgentStatus.SUCCESS, data={
            "factors": [
                {"name": "momentum_20", "metrics": {"sharpe": 0.34, "ic": 0.048}},
                {"name": "vol_reversal", "metrics": {"sharpe": -0.12, "ic": 0.01}},
            ],
            "best_sharpe": 0.34,
        }),
        2: AgentResult(status=AgentStatus.SUCCESS, data={
            "model_id": "gb_abc123",
            "model_type": "gradient_boosting",
            "sharpe": 19.5,
            "features_used": ["momentum_20", "vol_reversal"],
        }),
        3: AgentResult(status=AgentStatus.FAILED, error="timed out"),
    }

    # Replicate the collection logic from ooda.py
    tried_factors = []
    tried_models = []
    for step_id, r in results.items():
        if r.status != AgentStatus.SUCCESS:
            continue
        d = r.data
        if "factors" in d:
            for f in d["factors"]:
                tried_factors.append({
                    "name": f.get("name", ""),
                    "sharpe": f.get("metrics", {}).get("sharpe", 0),
                    "ic": f.get("metrics", {}).get("ic", 0),
                })
        if "model_id" in d:
            tried_models.append({
                "model_id": d.get("model_id", ""),
                "model_type": d.get("model_type", ""),
                "sharpe": d.get("sharpe", 0),
                "features": d.get("features_used", []),
            })

    assert len(tried_factors) == 2
    assert tried_factors[0]["name"] == "momentum_20"
    assert tried_factors[0]["sharpe"] == 0.34
    assert tried_factors[1]["name"] == "vol_reversal"

    assert len(tried_models) == 1
    assert tried_models[0]["model_id"] == "gb_abc123"
    assert tried_models[0]["sharpe"] == 19.5
    assert tried_models[0]["features"] == ["momentum_20", "vol_reversal"]


def test_planner_iteration_section_format():
    """Verify the Planner formats tried factors into the prompt."""
    iteration_context = [{
        "iteration": 1,
        "verdict": "iterate",
        "suggestion": "Try different factor families",
        "tried_factors": [
            {"name": "momentum_20", "sharpe": 0.34, "ic": 0.048},
            {"name": "vol_reversal", "sharpe": -0.12, "ic": 0.01},
        ],
        "tried_models": [
            {"model_type": "gradient_boosting", "sharpe": 19.5, "features": ["momentum_20", "vol_reversal"]},
        ],
    }]

    # Replicate the section-building logic from planner.py
    iteration_section = "\n\nPrevious iterations this cycle (DO NOT repeat the same factors or approaches):\n"
    for ic in iteration_context:
        iteration_section += (
            f"- Iteration {ic['iteration']}: {ic.get('verdict', '')} — "
            f"{ic.get('suggestion', '')}\n"
        )
        if ic.get("tried_factors"):
            iteration_section += "  Factors already tried (avoid these):\n"
            for f in ic["tried_factors"]:
                iteration_section += (
                    f"    - {f['name']} (sharpe={f.get('sharpe', 0):.3f}, "
                    f"ic={f.get('ic', 0):.4f})\n"
                )
        if ic.get("tried_models"):
            iteration_section += "  Models already trained:\n"
            for m in ic["tried_models"]:
                iteration_section += (
                    f"    - {m['model_type']} (sharpe={m.get('sharpe', 0):.2f}, "
                    f"features={m.get('features', [])})\n"
                )

    assert "DO NOT repeat" in iteration_section
    assert "momentum_20" in iteration_section
    assert "vol_reversal" in iteration_section
    assert "gradient_boosting" in iteration_section
    assert "sharpe=0.340" in iteration_section
    assert "ic=0.0480" in iteration_section
