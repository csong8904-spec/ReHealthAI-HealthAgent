"""Public simulation API.

v0.1 shipped an engine module that could not be imported at all (it referenced a
``get_intervention_plan`` that did not exist) and an entry point whose signature
did not match its own documentation.  This module is the single, documented way
to run a simulation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

from healthagent.agents.orchestrator import OrchestratorAgent
from healthagent.llm import LLMClient
from healthagent.model_params import ModelParams
from healthagent.models.intervention import (
    InterventionPlan,
    available_plans,
    resolve_plan,
)
from healthagent.models.patient_profile import PatientProfile
from healthagent.models.trajectory import SimulationResult
from healthagent.version import __version__

#: Persona used when no patient is supplied (the same one used in the demo).
DEFAULT_PATIENT: Dict[str, Any] = {
    "age": 52,
    "gender": "male",
    "occupation": "office_worker",
    "bmi": 27.5,
    "resting_hr": 78,
    "hrv_baseline": 38.0,
    "sleep_avg_hours": 6.2,
    "stress_level": "high",
    "motivation_score": 0.6,
    "habit_strength": 0.3,
    "social_support": 0.5,
    "primary_issue": "Pre-hypertension + insufficient sleep",
}

PatientLike = Union[PatientProfile, Dict[str, Any], None]
PlanLike = Union[InterventionPlan, str, None]


class SimulationEngine:
    """High-level entry point.

    Args:
        seed: Seed for every random component.  A seeded **offline** run is
            byte-for-byte reproducible for the same ``(seed, start_date,
            patient, plan, params)``.  With ``seed=None`` the run is not
            reproducible and the result says so.  LLM-assisted runs are never
            exactly reproducible (``reproducible=False``).
        offline: Force the rule-based adherence model (no network, no API key).
            ``None`` (default) = use the LLM when ``DEEPSEEK_API_KEY`` is set,
            otherwise fall back to offline mode automatically.
        params: Optional :class:`~healthagent.model_params.ModelParams` override.
        llm: Optional pre-built :class:`~healthagent.llm.LLMClient`.
        max_llm_calls: Hard cap on LLM requests for one run (default: horizon
            + 5).  Ignored in offline mode.

    Example:
        >>> engine = SimulationEngine(seed=42, offline=True)
        >>> result = engine.run_simulation(simulation_days=30)
        >>> result.compliance_rate > 0
        True
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        offline: Optional[bool] = None,
        params: Optional[ModelParams] = None,
        llm: Optional[LLMClient] = None,
        max_llm_calls: Optional[int] = None,
    ) -> None:
        self.seed = seed
        self.offline = offline
        self.params = params
        self.llm = llm
        self.max_llm_calls = max_llm_calls
        self._last_result: Optional[SimulationResult] = None

    # ------------------------------------------------------------------- public
    def run_simulation(
        self,
        patient: PatientLike = None,
        intervention_plan: PlanLike = None,
        simulation_days: Optional[int] = None,
        start_date: Optional[datetime] = None,
        custom_intervention: Optional[InterventionPlan] = None,
    ) -> SimulationResult:
        """Run one simulation.

        Args:
            patient: ``dict`` or :class:`PatientProfile`; defaults to
                :data:`DEFAULT_PATIENT`.
            intervention_plan: plan name (see
                :func:`~healthagent.models.available_plans`) or an
                :class:`InterventionPlan`; defaults to ``"hybrid"``.
            simulation_days: Horizon in days (1..730).  Defaults to the plan's
                ``duration_days``.  The plan object itself is never mutated.
            start_date: First simulated day.  Defaults to ``datetime.now()``.
            custom_intervention: Deprecated alias for ``intervention_plan``.

        Returns:
            :class:`~healthagent.models.trajectory.SimulationResult`
        """
        profile = (
            PatientProfile.from_dict(patient)
            if patient is not None
            else PatientProfile.from_dict(DEFAULT_PATIENT)
        )
        plan = resolve_plan(custom_intervention if custom_intervention is not None else intervention_plan)

        days = int(simulation_days) if simulation_days is not None else int(plan.duration_days)
        if not 1 <= days <= 730:
            raise ValueError(f"simulation_days must be within [1, 730], got {days}")

        orchestrator = OrchestratorAgent(
            patient=profile,
            intervention=plan,
            seed=self.seed,
            params=self.params,
            llm=self.llm,
            offline=self.offline,
            max_llm_calls=self.max_llm_calls,
        )
        result = orchestrator.run(days=days, start_date=start_date)
        self._last_result = result
        return result

    def quick_simulation(
        self,
        age: int = 52,
        bmi: float = 27.5,
        sleep_hours: float = 6.2,
        stress: str = "high",
        days: int = 90,
        intervention: str = "hybrid",
        resting_hr: int = 78,
        hrv_baseline: float = 38.0,
    ) -> SimulationResult:
        """Convenience wrapper for a one-off scenario (same persona as the demo)."""
        return self.run_simulation(
            patient={
                "age": age,
                "bmi": bmi,
                "sleep_avg_hours": sleep_hours,
                "stress_level": stress,
                "resting_hr": resting_hr,
                "hrv_baseline": hrv_baseline,
                "motivation_score": 0.6,
                "habit_strength": 0.3,
                "social_support": 0.5,
            },
            intervention_plan=intervention,
            simulation_days=days,
        )

    def get_last_result(self) -> Optional[SimulationResult]:
        return self._last_result

    @staticmethod
    def available_plans() -> list:
        return available_plans()


def run_simulation(
    patient: PatientLike = None,
    intervention_plan: PlanLike = None,
    simulation_days: Optional[int] = None,
    seed: Optional[int] = None,
    offline: Optional[bool] = None,
    start_date: Optional[datetime] = None,
) -> SimulationResult:
    """Functional wrapper around :class:`SimulationEngine`."""
    return SimulationEngine(seed=seed, offline=offline).run_simulation(
        patient=patient,
        intervention_plan=intervention_plan,
        simulation_days=simulation_days,
        start_date=start_date,
    )


__all__ = [
    "SimulationEngine",
    "run_simulation",
    "DEFAULT_PATIENT",
    "available_plans",
    "__version__",
]
