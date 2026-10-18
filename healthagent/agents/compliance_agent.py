"""Compliance agent - decides whether the simulated patient adheres today.

Two interchangeable backends:

``llm``
    One DeepSeek chat-completion per simulated day.  Temperature 0, JSON mode,
    bounded budget, and *automatic fallback* to the rule-based backend after
    repeated failures.  Because the API is not exactly reproducible, a run that
    uses it is reported as ``reproducible=False``.

``rule`` (default when no key is configured)
    A seeded logistic model over the same inputs.  Fully deterministic for a
    given ``(seed, input)`` pair, fast, and free - which makes demos and tests
    honest and cheap.
"""

from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass
from typing import List, Optional

from healthagent.llm import LLMClient
from healthagent.model_params import ModelParams
from healthagent.models.intervention import InterventionPlan
from healthagent.models.patient_profile import PatientProfile

logger = logging.getLogger(__name__)

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


@dataclass(frozen=True)
class ComplianceDecision:
    """Outcome of one adherence decision."""

    compliant: bool
    probability: float
    compliance_score: float  # 0.0 = none, 0.6 = partial, 1.0 = full
    key_factor: str = ""
    narrative: str = ""
    source: str = "rule"  # "rule" | "llm"

    def to_dict(self) -> dict:
        return {
            "compliant": self.compliant,
            "probability": round(self.probability, 3),
            "compliance_score": self.compliance_score,
            "key_factor": self.key_factor,
            "narrative": self.narrative,
            "source": self.source,
        }


class ComplianceAgent:
    """Models daily adherence with an optional LLM backend."""

    def __init__(
        self,
        patient: PatientProfile,
        intervention: InterventionPlan,
        seed: Optional[int] = None,
        params: Optional[ModelParams] = None,
        llm: Optional[LLMClient] = None,
        offline: bool = False,
        max_consecutive_failures: int = 3,
    ) -> None:
        self.patient = patient
        self.intervention = intervention
        self.params = params or ModelParams()
        self.rng = random.Random(seed)
        self.llm = llm
        self.offline = bool(offline)

        self.history: List[bool] = []
        self._llm_failures = 0
        self._llm_disabled = False
        self._warned = False
        self._max_failures = int(max_consecutive_failures)

    # ------------------------------------------------------------------ status
    @property
    def using_llm(self) -> bool:
        return bool(
            self.llm is not None
            and self.llm.available
            and not self.offline
            and not self._llm_disabled
        )

    # ------------------------------------------------------------------- public
    def decide(
        self,
        stress_level: float,
        motivation: float,
        day_of_week: int,
        sleep_quality: float,
        fatigue: float,
        previous_compliance: bool = True,
        day: int = 0,
    ) -> ComplianceDecision:
        """Return today's adherence decision."""
        if self.using_llm:
            try:
                decision = self._decide_with_llm(
                    stress_level=stress_level,
                    motivation=motivation,
                    day_of_week=day_of_week,
                    sleep_quality=sleep_quality,
                    fatigue=fatigue,
                    previous_compliance=previous_compliance,
                    day=day,
                )
                self.history.append(decision.compliant)
                return decision
            except Exception as exc:  # noqa: BLE001 - fall back on any failure
                self._llm_failures += 1
                if not self._warned:
                    logger.warning("LLM adherence backend failed (%s); using rule-based fallback", exc)
                    self._warned = True
                if self._llm_failures >= self._max_failures:
                    self._llm_disabled = True
                    logger.warning(
                        "Disabling the LLM backend for the rest of this run after %d failures",
                        self._llm_failures,
                    )

        decision = self._decide_rule_based(
            stress_level=stress_level,
            motivation=motivation,
            day_of_week=day_of_week,
            sleep_quality=sleep_quality,
            fatigue=fatigue,
            previous_compliance=previous_compliance,
        )
        self.history.append(decision.compliant)
        return decision

    # ---------------------------------------------------------------- rule mode
    def _logit(
        self,
        stress_level: float,
        motivation: float,
        day_of_week: int,
        sleep_quality: float,
        fatigue: float,
        previous_compliance: bool,
    ) -> float:
        params = self.params
        logit = params.compliance_intercept
        logit += params.compliance_motivation_weight * (motivation - 0.5)
        logit += params.compliance_stress_weight * (1.0 - stress_level)
        logit -= params.compliance_difficulty_weight * self.intervention.difficulty
        logit += params.compliance_habit_weight * (self.patient.habit_strength - 0.3)
        logit += params.compliance_social_weight * (self.patient.social_support - 0.5)
        logit += params.compliance_previous_weight * (1.0 if previous_compliance else -1.0)
        logit -= params.compliance_sleep_penalty * max(0.0, 0.5 - sleep_quality)
        logit -= params.compliance_fatigue_penalty * max(0.0, fatigue - 0.6)
        if day_of_week in (5, 6):  # weekend
            logit += params.compliance_weekend_bonus
        return logit

    def _decide_rule_based(
        self,
        stress_level: float,
        motivation: float,
        day_of_week: int,
        sleep_quality: float,
        fatigue: float,
        previous_compliance: bool,
    ) -> ComplianceDecision:
        probability = _sigmoid(
            self._logit(
                stress_level=stress_level,
                motivation=motivation,
                day_of_week=day_of_week,
                sleep_quality=sleep_quality,
                fatigue=fatigue,
                previous_compliance=previous_compliance,
            )
        )
        compliant = self.rng.random() < probability

        if not compliant:
            score = 0.0
        elif probability >= self.params.compliance_full_quality_threshold:
            score = 1.0
        else:
            score = 0.6

        return ComplianceDecision(
            compliant=compliant,
            probability=round(probability, 3),
            compliance_score=score,
            key_factor=self._rule_key_factor(
                stress_level, motivation, sleep_quality, fatigue
            ),
            narrative="",
            source="rule",
        )

    def _rule_key_factor(
        self, stress_level: float, motivation: float, sleep_quality: float, fatigue: float
    ) -> str:
        if stress_level > 0.70:
            return "high_stress"
        if motivation < 0.40:
            return "low_motivation"
        if self.intervention.difficulty > 0.60:
            return "high_plan_difficulty"
        if sleep_quality < 0.45:
            return "poor_sleep"
        if fatigue > 0.60:
            return "fatigue"
        return "stable_routine"

    # ----------------------------------------------------------------- LLM mode
    def _decide_with_llm(
        self,
        stress_level: float,
        motivation: float,
        day_of_week: int,
        sleep_quality: float,
        fatigue: float,
        previous_compliance: bool,
        day: int,
    ) -> ComplianceDecision:
        assert self.llm is not None  # for type checkers

        consecutive = 0
        for complied in reversed(self.history):
            if complied:
                consecutive += 1
            else:
                break

        prompt = self._build_prompt(
            stress_level=stress_level,
            motivation=motivation,
            day_of_week=day_of_week,
            sleep_quality=sleep_quality,
            fatigue=fatigue,
            consecutive=consecutive,
            day=day,
        )
        payload = self.llm.complete_json(prompt, max_tokens=700)

        # ``compliance_quality`` is the authoritative field: models frequently
        # report ``complied: false`` together with ``quality: "partial"`` (i.e.
        # "did some of it"), and v0.2.0 wrongly scored that as zero.  Partial
        # adherence is real adherence and must reach the physiology model.
        scores = {"full": 1.0, "partial": 0.6, "none": 0.0}
        quality = str(payload.get("compliance_quality", "")).strip().lower()

        if quality in scores:
            score = scores[quality]
            compliant = score > 0.0
        else:
            compliant = bool(payload.get("complied", payload.get("compliant", False)))
            try:
                probability_hint = float(payload.get("compliance_probability", 0.5))
            except (TypeError, ValueError):
                probability_hint = 0.5
            if not compliant:
                score = 0.0
            elif probability_hint >= self.params.compliance_full_quality_threshold:
                score = 1.0
            else:
                score = 0.6

        try:
            probability = float(payload.get("compliance_probability", 0.5))
        except (TypeError, ValueError):
            probability = 0.5
        probability = max(0.0, min(1.0, probability))

        return ComplianceDecision(
            compliant=compliant,
            probability=round(probability, 3),
            compliance_score=score,
            key_factor=str(payload.get("key_factor", ""))[:120],
            narrative=str(payload.get("narrative", ""))[:400],
            source="llm",
        )

    def _build_prompt(
        self,
        stress_level: float,
        motivation: float,
        day_of_week: int,
        sleep_quality: float,
        fatigue: float,
        consecutive: int,
        day: int,
    ) -> str:
        weekday = _WEEKDAY_NAMES[day_of_week % 7]
        recent = json.dumps(self.history[-7:]) if self.history else "[]"
        rules = "; ".join(self.intervention.rules) or "(no explicit rules)"
        return f"""Simulate ONE day of adherence for a patient enrolled in a health intervention.

Patient
- age: {self.patient.age}, gender: {self.patient.gender}
- chronic stress: {self.patient.stress_level.value}
- motivation trait: {self.patient.motivation_score:.2f}, habit strength: {self.patient.habit_strength:.2f}
- primary issue: {self.patient.primary_issue or "not specified"}

Plan
- name: {self.intervention.name} (type: {self.intervention.intervention_type.value})
- difficulty: {self.intervention.difficulty:.2f} (0 easy, 1 very hard)
- rules: {rules}

Day {day} ({weekday})
- current stress: {stress_level:.2f} (0-1)
- sleep quality last night: {sleep_quality:.2f} (0-1)
- fatigue: {fatigue:.2f} (0-1)
- consecutive compliant days before today: {consecutive}
- adherence on the previous 7 days: {recent}

Return ONLY this JSON object:
{{"complied": true|false,
  "compliance_quality": "full"|"partial"|"none",
  "compliance_probability": 0.0-1.0,
  "key_factor": "<= 12 words",
  "narrative": "third-person, <= 60 words, today only"}}"""
