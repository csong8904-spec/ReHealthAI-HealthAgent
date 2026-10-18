"""Central, documented model coefficients.

Every hand-tuned number used by the simulation lives here (and nowhere else) so
that the model can be re-calibrated against real adherence / wearable data
without hunting through the agents.  None of these values is a validated
clinical parameter: they are plausible placeholders chosen so that the model
reproduces qualitative, well-known patterns (adherence decays with stress and
with plan difficulty; adherence improves physiology; chronically stressed
patients start from their own steady state instead of being structurally
doomed).

To change behaviour, build a modified copy::

    from dataclasses import replace
    from healthagent.model_params import ModelParams

    params = replace(ModelParams(), hrv_stress_excess_penalty=0.7)
    SimulationEngine(params=params)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


#: Per-intervention-type effect profile.  Values are the effect *at full
#: effectiveness and full compliance* (i.e. they are multiplied by
#: ``average_effectiveness * compliance_score`` at use sites, so their practical
#: magnitude is always smaller than the number below).
#:   stress_relief : reduction of the stress target (0..1 scale)
#:   sleep_gain    : extra sleep hours
#:   hrv_gain      : *relative* HRV gain (0.18 -> +18 %)
#:   rhr_gain      : resting-HR reduction in bpm
PLAN_EFFECT_PROFILES: Dict[str, Dict[str, float]] = {
    "sleep_optimization": {
        "stress_relief": 0.10,
        "sleep_gain": 1.60,
        "hrv_gain": 0.20,
        "rhr_gain": 3.0,
    },
    "cardio_fitness": {
        "stress_relief": 0.08,
        "sleep_gain": 0.40,
        "hrv_gain": 0.22,
        "rhr_gain": 8.0,
    },
    "stress_management": {
        "stress_relief": 0.22,
        "sleep_gain": 0.60,
        "hrv_gain": 0.18,
        "rhr_gain": 5.0,
    },
    "nutrition_plan": {
        "stress_relief": 0.05,
        "sleep_gain": 0.30,
        "hrv_gain": 0.10,
        "rhr_gain": 5.0,
    },
    "hybrid": {
        "stress_relief": 0.14,
        "sleep_gain": 1.00,
        "hrv_gain": 0.18,
        "rhr_gain": 6.0,
    },
}


@dataclass(frozen=True)
class ModelParams:
    """Immutable bundle of simulation coefficients."""

    # ---------------------------------------------------------------- emotion
    #: Stress deviation by weekday (Mon=0 .. Sun=6).
    dow_stress_modifiers: Tuple[float, ...] = (0.15, 0.05, 0.0, -0.05, -0.10, -0.20, -0.15)
    #: Weight of yesterday's stress (inertia) in today's value.
    stress_inertia: float = 0.30
    #: Stress added per hour of sleep below the patient's own average.
    stress_sleep_debt_weight: float = 0.06
    #: Stress added by poor sleep quality.
    stress_sleep_quality_weight: float = 0.15
    #: Probability / magnitude of a random daily stressor.
    stress_random_event_prob: float = 0.10
    stress_random_event_range: Tuple[float, float] = (0.10, 0.30)
    #: Stress relief at full effectiveness and full compliance.
    stress_relief_weight: float = 0.20
    stress_min: float = 0.05
    stress_max: float = 0.99

    # ------------------------------------------------------------- motivation
    motivation_inertia: float = 0.35
    motivation_compliance_bonus: float = 0.10
    motivation_noncompliance_penalty: float = 0.15
    #: (last_day, delta) segments modelling early enthusiasm -> mid slump.
    motivation_day_curve: Tuple[Tuple[int, float], ...] = (
        (7, 0.15),
        (21, -0.05),
        (45, -0.10),
        (10_000, 0.05),
    )
    motivation_noise: float = 0.10

    # ------------------------------------------------- compliance (rule mode)
    #: Logistic coefficients for the offline/fallback adherence model.  These
    #: are the values that should be replaced by a fitted model.
    compliance_intercept: float = 0.0
    compliance_motivation_weight: float = 2.20
    compliance_stress_weight: float = 1.40
    compliance_difficulty_weight: float = 1.60
    compliance_habit_weight: float = 1.20
    compliance_social_weight: float = 0.50
    compliance_previous_weight: float = 0.30
    compliance_weekend_bonus: float = 0.25
    compliance_sleep_penalty: float = 0.80
    compliance_fatigue_penalty: float = 0.80
    #: Probability above which a compliant day counts as "full" (score 1.0).
    compliance_full_quality_threshold: float = 0.75

    # -------------------------------------------------------------- physiology
    hrv_relaxation: float = 0.25
    #: Penalty applied to the *excess* stress above the patient's baseline, so
    #: that chronically stressed patients are not double-counted.
    hrv_stress_excess_penalty: float = 0.50
    hrv_noise_relative: float = 0.012
    hrv_min_ratio: float = 0.40
    hrv_max_ratio: float = 1.80

    sleep_relaxation: float = 0.35
    sleep_stress_excess_penalty: float = 1.00
    sleep_noise: float = 0.25
    sleep_min: float = 3.5
    sleep_max: float = 10.0
    #: Sleep duration considered fully restorative when computing quality.
    sleep_optimal_hours: float = 8.0

    #: Sleep quality is anchored at ``sleep_quality_base`` for the patient's
    #: *baseline* behaviour, so that "no adherence" means "no change".
    sleep_quality_base: float = 0.60
    sleep_quality_hours_scale: float = 0.25
    sleep_quality_hours_reference: float = 0.75
    sleep_quality_stress_weight: float = 0.30
    sleep_quality_effectiveness_scale: float = 0.15
    sleep_quality_effectiveness_reference: float = 0.25

    #: HRV multiplier per unit of sleep quality, anchored at the same baseline.
    hrv_quality_gain: float = 0.20
    hrv_quality_reference: float = 0.60

    rhr_relaxation: float = 0.30
    rhr_stress_excess_penalty: float = 8.0
    rhr_noise: float = 1.0
    rhr_min: int = 42
    rhr_max: int = 100

    # ------------------------------------------------------ intervention policy
    #: Minimum days between two non-urgent nudges.
    intervention_cooldown_days: int = 2
    #: Hard cap on nudges per rolling 30 days, to avoid alert fatigue.
    intervention_max_per_30_days: int = 8
    #: Minimum days between scheduled (low priority) check-ins.
    intervention_checkin_interval: int = 7
    #: Stress above which a day is treated as urgent (bypasses the cooldown).
    intervention_urgent_stress: float = 0.85
    intervention_elevated_stress: float = 0.65

    # ---------------------------------------------------------------- reporting
    #: Number of trailing days averaged for the headline improvement metrics.
    metric_window_days: int = 14

    #: Effect profile lookup (copied at construction so mutation is impossible).
    plan_profiles: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {k: dict(v) for k, v in PLAN_EFFECT_PROFILES.items()}
    )

    def profile_for(self, intervention_type: str) -> Dict[str, float]:
        """Return the effect profile for an intervention type (fallback: hybrid)."""
        return self.plan_profiles.get(intervention_type, self.plan_profiles["hybrid"])
