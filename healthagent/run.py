"""Optional DeerFlow / agent-framework integration.

v0.1 hard-coded an author-local Windows path, so this module was unusable
anywhere else and could not even be imported from an installed package.  It now
delegates to the public API and has no machine-specific paths.

The tool returns simulation output only - it is **not** a diagnostic or
treatment recommendation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from healthagent.engine.simulation_engine import SimulationEngine
from healthagent.version import __version__


def run_health_simulation(
    age: int = 52,
    stress: str = "high",
    sleep_hours: float = 6.2,
    bmi: float = 27.5,
    days: int = 30,
    primary_issue: str = "Pre-hypertension + insufficient sleep",
    seed: int = 42,
    offline: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run a simulation and return a JSON-serialisable summary for an agent.

    Args:
        age: patient age in years.
        stress: ``low`` / ``medium`` / ``high``.
        sleep_hours: average nightly sleep.
        bmi: body-mass index.
        days: horizon in days (1..365).
        primary_issue: free-text description.
        seed: RNG seed.
        offline: force the deterministic rule model (``None`` = auto-detect).
    """
    days = max(1, min(int(days), 365))
    engine = SimulationEngine(seed=seed, offline=offline)
    result = engine.run_simulation(
        patient={
            "age": age,
            "bmi": bmi,
            "sleep_avg_hours": sleep_hours,
            "stress_level": stress,
            "primary_issue": primary_issue,
        },
        intervention_plan="hybrid",
        simulation_days=days,
    )

    summary = result.summary()
    highlights = [
        {
            "day": state.day,
            "compliant": state.compliance,
            "emotion": state.emotion_state,
            "stress": round(state.stress_level, 2),
            "sleep_hours": round(state.sleep_hours, 1),
            "hrv": round(state.hrv, 1),
            "resting_hr": state.resting_hr,
            "nudge": state.intervention_message if state.intervention_triggered else None,
        }
        for state in result.trajectory
        if state.day == 1 or state.day % max(1, days // 7) == 0
    ]

    return {
        "version": __version__,
        "mode": result.mode,
        "simulation_days": result.simulation_days,
        "summary": summary,
        "assessment": _assessment(summary),
        "daily_highlights": highlights,
        "disclaimer": "Research simulation only. Not medical advice.",
    }


def _assessment(summary: Dict[str, Any]) -> str:
    """Plain-language reading of the simulated summary (no clinical claims)."""
    parts = []
    adherence = summary["compliance_rate"]
    if adherence >= 0.8:
        parts.append(f"Simulated adherence is high ({adherence:.0%}).")
    elif adherence >= 0.5:
        parts.append(f"Simulated adherence is moderate ({adherence:.0%}).")
    else:
        parts.append(f"Simulated adherence is low ({adherence:.0%}); engagement is the bottleneck.")

    sleep_delta = summary["sleep_improvement"]
    if sleep_delta > 0.3:
        parts.append(f"Simulated sleep rises by {sleep_delta:.1f} h.")
    elif sleep_delta < -0.3:
        parts.append(f"Simulated sleep falls by {abs(sleep_delta):.1f} h.")
    else:
        parts.append("Simulated sleep is essentially unchanged.")

    hrv_delta = summary["hrv_change"]
    if hrv_delta > 2:
        parts.append(f"Simulated HRV rises by {hrv_delta:.1f} ms.")
    elif hrv_delta < -2:
        parts.append(f"Simulated HRV falls by {abs(hrv_delta):.1f} ms.")
    return " ".join(parts)


def get_tool_definition() -> Dict[str, Any]:
    """Return a tool schema describing :func:`run_health_simulation`."""
    return {
        "name": "health_agent_simulation",
        "description": (
            "Run a behavioural health-intervention simulation. Returns simulated "
            "adherence and biomarker trajectories for a hypothetical patient. "
            "Research/illustrative use only - never a diagnosis or treatment plan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "minimum": 10, "maximum": 120},
                "stress": {"type": "string", "enum": ["low", "medium", "high"]},
                "sleep_hours": {"type": "number", "minimum": 3, "maximum": 14},
                "bmi": {"type": "number", "minimum": 10, "maximum": 70},
                "days": {"type": "integer", "minimum": 1, "maximum": 365},
                "primary_issue": {"type": "string"},
                "seed": {"type": "integer"},
            },
            "required": ["age", "stress", "days"],
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_health_simulation(days=7, offline=True), ensure_ascii=False, indent=2))
