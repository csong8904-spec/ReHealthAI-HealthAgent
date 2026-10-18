"""Emotion agent - stress, motivation and fatigue dynamics.

The agent is a deterministic (seeded) state machine.  It is *not* an LLM: the
LLM only enters the loop through :class:`~healthagent.agents.compliance_agent.
ComplianceAgent`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from healthagent.model_params import ModelParams
from healthagent.models.patient_profile import PatientProfile


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class EmotionState:
    """Emotional state for one simulated day."""

    emotion_state: str
    stress_level: float  # 0.0 - 1.0
    motivation: float  # 0.0 - 1.0
    fatigue: float  # 0.0 - 1.0

    def to_dict(self) -> dict:
        return {
            "emotion_state": self.emotion_state,
            "stress_level": round(self.stress_level, 3),
            "motivation": round(self.motivation, 3),
            "fatigue": round(self.fatigue, 3),
        }


class EmotionAgent:
    """Simulates day-to-day emotional dynamics.

    Inputs (all passed by the orchestrator): yesterday's compliance, last
    night's sleep.  The agent also takes the intervention's ``effectiveness``
    and the realised ``compliance_score`` so that *adhering to the plan actually
    lowers stress* - the feedback edge that was missing in v0.1.
    """

    def __init__(
        self,
        patient: PatientProfile,
        seed: Optional[int] = None,
        params: Optional[ModelParams] = None,
    ) -> None:
        self.patient = patient
        self.params = params or ModelParams()
        self.rng = random.Random(seed)

        self._stress_baseline = patient.stress_baseline
        self._previous_stress = self._stress_baseline
        self._motivation_baseline = patient.motivation_score
        self._previous_motivation = patient.motivation_score

    # ------------------------------------------------------------------ public
    def simulate(
        self,
        day: int,
        day_of_week: int,
        previous_compliance: bool,
        sleep_hours: float,
        sleep_quality: float,
        compliance_score: float = 0.0,
        effectiveness: float = 0.0,
    ) -> EmotionState:
        stress = self._calculate_stress(
            day_of_week=day_of_week,
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
            compliance_score=compliance_score,
            effectiveness=effectiveness,
        )
        motivation = self._calculate_motivation(previous_compliance, day)
        fatigue = self._calculate_fatigue(sleep_hours, stress)

        state = EmotionState(
            emotion_state=self._determine_emotion_state(stress, motivation, fatigue),
            stress_level=stress,
            motivation=motivation,
            fatigue=fatigue,
        )

        self._previous_stress = stress
        self._previous_motivation = motivation
        return state

    # --------------------------------------------------------------- internals
    def _calculate_stress(
        self,
        day_of_week: int,
        sleep_hours: float,
        sleep_quality: float,
        compliance_score: float,
        effectiveness: float,
    ) -> float:
        params = self.params

        target = self._stress_baseline
        target += params.dow_stress_modifiers[day_of_week % 7]

        sleep_debt = max(0.0, self.patient.sleep_avg_hours - sleep_hours)
        target += sleep_debt * params.stress_sleep_debt_weight
        target += max(0.0, 0.6 - sleep_quality) * params.stress_sleep_quality_weight

        if self.rng.random() < params.stress_random_event_prob:
            target += self.rng.uniform(*params.stress_random_event_range)

        # NEW: successful adherence relieves stress (scaled by how effective the
        # plan is for this patient).
        target -= params.stress_relief_weight * effectiveness * compliance_score

        target = _clamp(target, params.stress_min, params.stress_max)

        stress = params.stress_inertia * self._previous_stress + (
            1.0 - params.stress_inertia
        ) * target
        return _clamp(stress, params.stress_min, params.stress_max)

    def _calculate_motivation(self, previous_compliance: bool, day: int) -> float:
        params = self.params

        motivation = self._motivation_baseline
        if previous_compliance:
            motivation += params.motivation_compliance_bonus
        else:
            motivation -= params.motivation_noncompliance_penalty

        for last_day, delta in params.motivation_day_curve:
            if day <= last_day:
                motivation += delta
                break

        motivation += self.rng.uniform(-params.motivation_noise, params.motivation_noise)
        motivation = params.motivation_inertia * self._previous_motivation + (
            1.0 - params.motivation_inertia
        ) * motivation
        return _clamp(motivation, 0.0, 1.0)

    def _calculate_fatigue(self, sleep_hours: float, stress: float) -> float:
        sleep_deficit = max(0.0, self.params.sleep_optimal_hours - sleep_hours)
        fatigue = (
            0.12
            + 0.09 * sleep_deficit
            + 0.35 * stress
            + self.rng.uniform(-0.05, 0.08)
        )
        return _clamp(fatigue, 0.0, 1.0)

    @staticmethod
    def _determine_emotion_state(stress: float, motivation: float, fatigue: float) -> str:
        if stress > 0.75:
            return "anxious" if motivation > 0.6 else "stressed"
        if fatigue > 0.65:
            return "frustrated" if stress > 0.4 else "fatigued"
        if motivation > 0.70:
            return "motivated" if stress < 0.35 else "hopeful"
        if stress < 0.35 and motivation > 0.50:
            return "content"
        if stress < 0.45 and fatigue < 0.45:
            return "calm"
        if stress >= fatigue and stress >= motivation:
            return "stressed"
        if fatigue >= motivation:
            return "fatigued"
        return "calm"
