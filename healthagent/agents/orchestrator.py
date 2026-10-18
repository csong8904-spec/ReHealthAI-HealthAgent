"""Orchestrator - runs the day-by-day simulation loop.

The loop is deliberately explicit: each day, emotion feeds adherence, adherence
feeds physiology, physiology feeds the nudge policy, and yesterday's adherence
feeds back into today's emotion and physiology.  That closed loop is what v0.1
was missing.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Dict, List, Optional

from healthagent.agents.compliance_agent import ComplianceAgent, ComplianceDecision
from healthagent.agents.emotion_agent import EmotionAgent, EmotionState
from healthagent.agents.intervention_agent import InterventionAgent, InterventionDecision
from healthagent.agents.physiology_agent import PhysiologyAgent, PhysiologyState
from healthagent.llm import LLMClient
from healthagent.model_params import ModelParams
from healthagent.models.intervention import InterventionPlan
from healthagent.models.patient_profile import PatientProfile
from healthagent.models.trajectory import DailyState, SimulationResult
from healthagent.version import __version__

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SimulationContext:
    """Mutable state passed between the agents for one day."""

    day: int
    day_of_week: int  # 0 = Monday
    date: datetime

    prev_compliance: bool = True
    prev_compliance_score: float = 0.0
    prev_sleep_hours: float = 7.0
    prev_sleep_quality: float = 0.6

    emotion_state: Optional[EmotionState] = None
    compliance_decision: Optional[ComplianceDecision] = None
    physiology_state: Optional[PhysiologyState] = None
    intervention_decision: Optional[InterventionDecision] = None


class OrchestratorAgent:
    """Coordinates the four agents over a simulated period."""

    def __init__(
        self,
        patient: PatientProfile,
        intervention: InterventionPlan,
        seed: Optional[int] = None,
        params: Optional[ModelParams] = None,
        llm: Optional[LLMClient] = None,
        offline: Optional[bool] = None,
        max_llm_calls: Optional[int] = None,
    ) -> None:
        self.patient = patient
        self.intervention = intervention
        self.params = params or ModelParams()
        self.seed = seed

        if offline is None:
            offline = _env_flag("REHEALTH_OFFLINE")
        if not offline and llm is None:
            llm = LLMClient.from_env()
        if not offline and llm is not None and not llm.available:
            offline = True
        self.offline = bool(offline)
        self.llm = llm
        self.max_llm_calls = max_llm_calls

        self.emotion_agent = EmotionAgent(
            patient, seed=self._derive_seed("emotion"), params=self.params
        )
        self.compliance_agent = ComplianceAgent(
            patient,
            intervention,
            seed=self._derive_seed("compliance"),
            params=self.params,
            llm=None if self.offline else llm,
            offline=self.offline,
        )
        self.physiology_agent = PhysiologyAgent(
            patient, intervention, seed=self._derive_seed("physiology"), params=self.params
        )
        self.intervention_agent = InterventionAgent(
            patient, intervention, seed=self._derive_seed("intervention"), params=self.params
        )

        self.trajectory: List[DailyState] = []
        self.start_date: Optional[datetime] = None
        self._used_llm = False

    # ------------------------------------------------------------------- seeds
    def _derive_seed(self, name: str) -> Optional[int]:
        """Stable per-agent seed (``hash()`` is salted per process, so use SHA-256)."""
        if self.seed is None:
            return None
        digest = hashlib.sha256(f"{self.seed}:{name}".encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big")

    # --------------------------------------------------------------------- run
    def run(
        self, days: Optional[int] = None, start_date: Optional[datetime] = None
    ) -> SimulationResult:
        simulation_days = int(days if days is not None else self.intervention.duration_days)
        if not 1 <= simulation_days <= 730:
            raise ValueError(f"days must be within [1, 730], got {simulation_days}")

        self.start_date = (start_date or datetime.now()).replace(microsecond=0)
        self.trajectory = []
        self._used_llm = False

        # Hard call budget: one call per simulated day plus a small retry slack.
        # Without this, a long horizon against a paid API is an unbounded cost.
        if not self.offline and self.llm is not None:
            budget = self.max_llm_calls
            if budget is None:
                budget = simulation_days + 5
            if getattr(self.llm, "max_calls", 0) is None:
                try:
                    self.llm.max_calls = budget
                except AttributeError:  # pragma: no cover - read-only stub
                    pass

        context = SimulationContext(
            day=0,
            day_of_week=self.start_date.weekday(),
            date=self.start_date,
            prev_sleep_hours=self.patient.sleep_avg_hours,
        )

        for day in range(1, simulation_days + 1):
            context.day = day
            context.date = self.start_date + timedelta(days=day - 1)
            context.day_of_week = context.date.weekday()

            self._simulate_day(context)
            self.trajectory.append(self._create_daily_state(context))

            context.prev_compliance = context.compliance_decision.compliant  # type: ignore[union-attr]
            context.prev_compliance_score = context.compliance_decision.compliance_score  # type: ignore[union-attr]
            context.prev_sleep_hours = context.physiology_state.sleep_hours  # type: ignore[union-attr]
            context.prev_sleep_quality = context.physiology_state.sleep_quality  # type: ignore[union-attr]

        return self._build_result(simulation_days)

    # ----------------------------------------------------------------- per day
    def _simulate_day(self, context: SimulationContext) -> SimulationContext:
        # 1. Emotion (uses YESTERDAY's adherence -> stress feedback)
        context.emotion_state = self.emotion_agent.simulate(
            day=context.day,
            day_of_week=context.day_of_week,
            previous_compliance=context.prev_compliance,
            sleep_hours=context.prev_sleep_hours,
            sleep_quality=context.prev_sleep_quality,
            compliance_score=context.prev_compliance_score,
            effectiveness=self.intervention.average_effectiveness,
        )

        # 2. Adherence decision (LLM or rule-based)
        context.compliance_decision = self.compliance_agent.decide(
            stress_level=context.emotion_state.stress_level,
            motivation=context.emotion_state.motivation,
            day_of_week=context.day_of_week,
            sleep_quality=context.prev_sleep_quality,
            fatigue=context.emotion_state.fatigue,
            previous_compliance=context.prev_compliance,
            day=context.day,
        )
        if context.compliance_decision.source == "llm":
            self._used_llm = True

        # 3. Physiology reacts to today's stress and adherence
        context.physiology_state = self.physiology_agent.simulate(
            stress_level=context.emotion_state.stress_level,
            compliance=context.compliance_decision.compliant,
            compliance_score=context.compliance_decision.compliance_score,
            day=context.day,
        )

        # 4. Nudge policy
        trends = self.physiology_agent.get_trends()
        context.intervention_decision = self.intervention_agent.evaluate(
            day=context.day,
            compliance_probability=context.compliance_decision.probability,
            stress_level=context.emotion_state.stress_level,
            recent_compliance=context.prev_compliance,
            hrv_trend=trends.get("hrv_change", 0.0),
            sleep_trend=trends.get("sleep_hours_change", 0.0),
        )
        return context

    # ------------------------------------------------------------------ output
    def _create_daily_state(self, context: SimulationContext) -> DailyState:
        weekday = WEEKDAY_NAMES[context.day_of_week]
        emotion = context.emotion_state
        compliance = context.compliance_decision
        phys = context.physiology_state
        nudge = context.intervention_decision
        assert emotion and compliance and phys and nudge  # for type checkers

        narrative = compliance.narrative or (
            f"Day {context.day} ({weekday}): felt {emotion.emotion_state}; "
            f"{'followed' if compliance.compliant else 'skipped'} the plan "
            f"(stress {emotion.stress_level:.0%}, sleep {phys.sleep_hours:.1f} h)."
        )

        return DailyState(
            day=context.day,
            day_of_week=context.day_of_week + 1,  # 1 = Monday
            date=context.date,
            emotion_state=emotion.emotion_state,
            stress_level=emotion.stress_level,
            motivation=emotion.motivation,
            compliance=compliance.compliant,
            compliance_score=compliance.compliance_score,
            sleep_hours=phys.sleep_hours,
            sleep_quality=phys.sleep_quality,
            hrv=phys.hrv,
            resting_hr=phys.resting_hr,
            intervention_triggered=nudge.triggered,
            intervention_message=nudge.message,
            narrative=narrative,
            key_factor=compliance.key_factor,
        )

    def _build_result(self, simulation_days: int) -> SimulationResult:
        if not self.trajectory:
            return SimulationResult()

        window_size = min(self.params.metric_window_days, len(self.trajectory))
        window = self.trajectory[-window_size:]
        total = len(self.trajectory)
        full_days = sum(1 for d in self.trajectory if d.compliance_score >= 0.999)
        partial_days = sum(
            1 for d in self.trajectory if 0.0 < d.compliance_score < 0.999
        )

        return SimulationResult(
            trajectory=self.trajectory,
            compliance_rate=sum(1 for d in self.trajectory if d.compliance) / total,
            full_compliance_rate=full_days / total,
            partial_compliance_rate=partial_days / total,
            average_sleep_hours=mean(d.sleep_hours for d in self.trajectory),
            average_stress=mean(d.stress_level for d in self.trajectory),
            sleep_improvement=mean(d.sleep_hours for d in window)
            - self.patient.sleep_avg_hours,
            hrv_change=mean(d.hrv for d in window) - self.physiology_agent.hrv_baseline,
            resting_hr_change=mean(d.resting_hr for d in window) - self.patient.resting_hr,
            intervention_count=self.intervention_agent.intervention_count,
            simulation_days=simulation_days,
            metrics_window_days=window_size,
            start_date=self.start_date,
            end_date=self.trajectory[-1].date,
            mode="llm" if self._used_llm else "offline",
            seed=self.seed,
            # A run is only reproducible when it is fully seeded AND offline: the
            # LLM is not deterministic even at temperature 0.
            reproducible=(self.seed is not None) and not self._used_llm,
            patient=self._patient_dict(),
            intervention=self._intervention_dict(),
            baseline={
                "sleep_hours": round(float(self.patient.sleep_avg_hours), 2),
                "hrv": round(float(self.physiology_agent.hrv_baseline), 2),
                "resting_hr": int(self.patient.resting_hr),
                "stress": round(float(self.patient.stress_baseline), 3),
            },
            version=__version__,
        )

    def _patient_dict(self) -> Dict[str, Any]:
        return {
            "name": self.patient.name,
            "age": self.patient.age,
            "gender": self.patient.gender,
            "occupation": self.patient.occupation,
            "bmi": self.patient.bmi,
            "resting_hr": self.patient.resting_hr,
            "hrv_baseline": self.physiology_agent.hrv_baseline,
            "sleep_avg_hours": self.patient.sleep_avg_hours,
            "exercise_per_week": self.patient.exercise_per_week,
            "wearable": self.patient.wearable,
            "stress_level": self.patient.stress_level.value,
            "motivation_score": self.patient.motivation_score,
            "habit_strength": self.patient.habit_strength,
            "social_support": self.patient.social_support,
            "primary_issue": self.patient.primary_issue,
            "age_group": self.patient.age_group,
        }

    def _intervention_dict(self) -> Dict[str, Any]:
        return {
            "name": self.intervention.name,
            "type": self.intervention.intervention_type.value,
            "duration_days": self.intervention.duration_days,
            "intensity": self.intervention.intensity,
            "difficulty": self.intervention.difficulty,
            "average_effectiveness": self.intervention.average_effectiveness,
            "nudge_frequency": self.intervention.nudge_frequency,
            "rules": list(self.intervention.rules),
        }
