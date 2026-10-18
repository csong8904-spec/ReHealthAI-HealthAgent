"""Physiology agent - maps behaviour and emotion onto biomarkers.

v0.1 applied the *absolute* stress level as a penalty, which double-counted
chronic stress: a patient whose ``sleep_avg_hours`` and ``hrv_baseline`` were
already measured under high stress was penalised again every single day, so the
model could only produce deterioration for exactly the population the product
targets.  v0.2 uses the **excess** stress above the patient's own baseline, and
effects are relative to each patient's baseline instead of absolute constants.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Tuple

from healthagent.model_params import ModelParams
from healthagent.models.intervention import InterventionPlan
from healthagent.models.patient_profile import PatientProfile

#: Population-plausible resting HRV by age band, used when the patient has no
#: measured baseline.
HRV_BY_AGE_GROUP = {
    "young_adult": 62.0,
    "middle_aged": 46.0,
    "older_adult": 36.0,
}

_STRESS_FACTOR = {"low": 1.10, "medium": 1.00, "high": 0.88}


def estimate_hrv_baseline(patient: PatientProfile) -> float:
    """Estimate an HRV baseline (ms) from age group, BMI and chronic stress."""
    base = HRV_BY_AGE_GROUP.get(patient.age_group, 46.0)
    bmi_factor = 1.0 - max(0.0, patient.bmi - 25.0) * 0.015
    stress_factor = _STRESS_FACTOR.get(patient.stress_level.value, 1.0)
    return max(10.0, base * bmi_factor * stress_factor)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class PhysiologyState:
    """Biomarkers for one simulated day."""

    hrv: float  # ms
    resting_hr: int  # bpm
    sleep_hours: float
    sleep_quality: float  # 0-1

    def to_dict(self) -> dict:
        return {
            "hrv": round(self.hrv, 2),
            "resting_hr": self.resting_hr,
            "sleep_hours": round(self.sleep_hours, 2),
            "sleep_quality": round(self.sleep_quality, 3),
        }


class PhysiologyAgent:
    """Deterministic biomarker model with mean-reverting targets."""

    def __init__(
        self,
        patient: PatientProfile,
        intervention: InterventionPlan,
        seed: Optional[int] = None,
        params: Optional[ModelParams] = None,
    ) -> None:
        self.patient = patient
        self.intervention = intervention
        self.params = params or ModelParams()
        self.rng = random.Random(seed)

        self.hrv_baseline = (
            float(patient.hrv_baseline)
            if patient.hrv_baseline is not None
            else estimate_hrv_baseline(patient)
        )
        self.profile = self.params.profile_for(intervention.intervention_type.value)

        self._hrv = self.hrv_baseline
        self._resting_hr = float(patient.resting_hr)
        self._sleep_hours = float(patient.sleep_avg_hours)
        self._sleep_quality = 0.6

        self.hrv_history = [self._hrv]
        self.rhr_history = [self._resting_hr]
        self.sleep_history = [self._sleep_hours]

    # ------------------------------------------------------------------ public
    def simulate(
        self,
        stress_level: float,
        compliance: bool,
        compliance_score: float,
        day: int = 1,
    ) -> PhysiologyState:
        """Advance the biomarker state by one day."""
        effectiveness = self.intervention.average_effectiveness * compliance_score
        stress_excess = max(0.0, stress_level - self.patient.stress_baseline)

        sleep_hours, sleep_quality = self._simulate_sleep(stress_excess, effectiveness)
        hrv = self._simulate_hrv(stress_excess, effectiveness, sleep_quality)
        resting_hr = self._simulate_resting_hr(stress_excess, effectiveness)

        self._hrv = hrv
        self._resting_hr = resting_hr
        self._sleep_hours = sleep_hours
        self._sleep_quality = sleep_quality

        self.hrv_history.append(hrv)
        self.rhr_history.append(resting_hr)
        self.sleep_history.append(sleep_hours)

        return PhysiologyState(
            hrv=hrv,
            resting_hr=int(round(resting_hr)),
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
        )

    def get_trends(self) -> dict:
        """Short-window trends used by the intervention agent."""
        if len(self.hrv_history) < 2:
            return {}
        window = min(7, len(self.hrv_history))
        hrv_trend = self.hrv_history[-1] - sum(self.hrv_history[-window:-1]) / (window - 1)
        rhr_trend = self.rhr_history[-1] - sum(self.rhr_history[-window:-1]) / (window - 1)
        sleep_trend = self.sleep_history[-1] - sum(self.sleep_history[-window:-1]) / (
            window - 1
        )
        return {
            "hrv_change": round(hrv_trend, 2),
            "resting_hr_change": round(rhr_trend, 2),
            "sleep_hours_change": round(sleep_trend, 2),
        }

    # --------------------------------------------------------------- internals
    def _simulate_sleep(
        self, stress_excess: float, effectiveness: float
    ) -> Tuple[float, float]:
        params = self.params
        target = (
            self.patient.sleep_avg_hours
            + self.profile["sleep_gain"] * effectiveness
            - params.sleep_stress_excess_penalty * stress_excess
        )
        sleep_hours = (
            self._sleep_hours
            + params.sleep_relaxation * (target - self._sleep_hours)
            + self.rng.gauss(0.0, params.sleep_noise)
        )
        sleep_hours = _clamp(sleep_hours, params.sleep_min, params.sleep_max)

        hours_quality = _clamp(
            1.0
            - abs(sleep_hours - params.sleep_optimal_hours) / params.sleep_optimal_hours,
            0.0,
            1.0,
        )
        # Anchored at the patient's baseline behaviour: adherence (and only
        # adherence) moves quality away from ``sleep_quality_base``.
        quality = params.sleep_quality_base
        quality += params.sleep_quality_hours_scale * (
            hours_quality - params.sleep_quality_hours_reference
        )
        quality -= params.sleep_quality_stress_weight * stress_excess
        quality += params.sleep_quality_effectiveness_scale * (
            effectiveness - params.sleep_quality_effectiveness_reference
        )
        quality += self.rng.uniform(-0.05, 0.05)
        quality = _clamp(quality, 0.05, 1.0)
        return sleep_hours, quality

    def _simulate_hrv(
        self, stress_excess: float, effectiveness: float, sleep_quality: float
    ) -> float:
        params = self.params
        target = self.hrv_baseline * (
            1.0
            - params.hrv_stress_excess_penalty * stress_excess
            + self.profile["hrv_gain"] * effectiveness
        )
        target *= 1.0 + params.hrv_quality_gain * (
            sleep_quality - params.hrv_quality_reference
        )

        hrv = (
            self._hrv
            + params.hrv_relaxation * (target - self._hrv)
            + self.rng.gauss(0.0, self.hrv_baseline * params.hrv_noise_relative)
        )
        return _clamp(
            hrv,
            self.hrv_baseline * params.hrv_min_ratio,
            self.hrv_baseline * params.hrv_max_ratio,
        )

    def _simulate_resting_hr(self, stress_excess: float, effectiveness: float) -> float:
        params = self.params
        target = (
            self.patient.resting_hr
            - self.profile["rhr_gain"] * effectiveness
            + params.rhr_stress_excess_penalty * stress_excess
        )
        rhr = (
            self._resting_hr
            + params.rhr_relaxation * (target - self._resting_hr)
            + self.rng.gauss(0.0, params.rhr_noise)
        )
        return _clamp(rhr, params.rhr_min, params.rhr_max)
