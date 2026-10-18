"""Intervention agent - risk detection and behavioural nudges.

v0.1 compared priorities with ``max(priority, "medium")`` on *strings*.  In
Python ``max("high", "medium") == "medium"`` and ``max("high", "low") == "low"``,
so a high-severity day could be silently downgraded and then swallowed by the
cooldown.  Priorities are now an :class:`IntEnum`, and urgent days always bypass
the cooldown.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Deque, Dict, List, Optional, Tuple

from healthagent.model_params import ModelParams
from healthagent.models.intervention import InterventionPlan
from healthagent.models.patient_profile import PatientProfile


class Priority(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2

    def label(self) -> str:
        return self.name.lower()


MESSAGE_CATALOG: Dict[str, Dict[str, List[str]]] = {
    "sleep_optimization": {
        "encouragement": [
            "Your sleep pattern is improving - keep the routine steady.",
            "Consistency is paying off; your body clock is adapting.",
            "Two good nights in a row. Nice work.",
        ],
        "reminder": [
            "Wind-down routine starts in 30 minutes.",
            "Screens off one hour before bed tonight.",
            "Target lights-out time is approaching.",
        ],
        "warning": [
            "Sleep quality has slipped for a few nights - let's refocus.",
            "Stress is eating into your sleep. Try the breathing exercise.",
            "Several late nights in a row; let's reset the schedule.",
        ],
        "intervention": [
            "Let's review your bedtime routine together.",
            "Want to adjust your target bedtime this week?",
        ],
    },
    "cardio_fitness": {
        "encouragement": [
            "Resting heart rate is trending the right way.",
            "Good week of activity - your cardiovascular system notices.",
            "You are building real fitness momentum.",
        ],
        "reminder": [
            "Today's walk is still on the plan.",
            "Active break time - ten minutes is enough to count.",
            "Resistance session scheduled for today.",
        ],
        "warning": [
            "Activity has dropped off this week.",
            "Resting heart rate is up; a short walk can help.",
            "Missed sessions are adding up - let's restart small.",
        ],
        "intervention": [
            "Let's shorten the sessions so they fit your week.",
            "Should we swap to two shorter walks per day?",
        ],
    },
    "stress_management": {
        "encouragement": [
            "Stress is trending down - the practice is working.",
            "You handled a hard week with the tools we set up.",
            "Steady mindfulness practice - well done.",
        ],
        "reminder": [
            "Ten-minute mindfulness session is due.",
            "Three slow breaths before the next meeting.",
            "Your screen-free evening is tonight.",
        ],
        "warning": [
            "Stress is climbing; protect some recovery time today.",
            "Early warning signs detected - prioritise sleep tonight.",
            "Do not skip the breathing practice today.",
        ],
        "intervention": [
            "Let's add one extra recovery block this week.",
            "Want to try a longer relaxation session?",
        ],
    },
    "nutrition_plan": {
        "encouragement": [
            "Food logging is consistent - that is the hard part.",
            "Two alcohol-free days done. Keep going.",
            "Your meal pattern is stabilising.",
        ],
        "reminder": [
            "Remember the low-salt swap at dinner tonight.",
            "Log today's meals while they are fresh.",
            "Plan tomorrow's lunch before you get hungry.",
        ],
        "warning": [
            "Logging has stopped for three days - let's restart.",
            "Sodium crept back up this week.",
            "Missed logs make the plan impossible to tune.",
        ],
        "intervention": [
            "Let's simplify the plan to three rules for two weeks.",
            "Which meal is hardest to keep? We can swap it.",
        ],
    },
    "hybrid": {
        "encouragement": [
            "Several markers are improving at once - good work.",
            "The combined routine is holding together.",
            "Sustainable habits are forming. Keep it up.",
        ],
        "reminder": [
            "Today's commitments: walk, bedtime, mindfulness.",
            "Small daily actions are what move the markers.",
            "Check in with your plan before the evening.",
        ],
        "warning": [
            "Several indicators need attention this week.",
            "The routine has slipped - pick one habit to restore.",
            "Stress and sleep are both trending the wrong way.",
        ],
        "intervention": [
            "Let's reassess which pillar matters most right now.",
            "Time for a structured check-in.",
        ],
    },
}

_FALLBACK_CATEGORY = "hybrid"


@dataclass
class InterventionDecision:
    """Outcome of one nudge decision."""

    triggered: bool
    message: Optional[str]
    intervention_type: str
    priority: Priority
    reason: str

    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "message": self.message,
            "intervention_type": self.intervention_type,
            "priority": self.priority.label(),
            "reason": self.reason,
        }


class InterventionAgent:
    """Rule-based risk detection and nudge selection (no LLM)."""

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

        self.last_intervention_day = -10_000
        self.intervention_count = 0
        self._nudge_days: List[int] = []
        self._recent_messages: Deque[str] = deque(maxlen=4)
        self._last_message: Optional[str] = None

        self.non_compliance_streak = 0
        self.compliance_streak = 0

    # ------------------------------------------------------------------ public
    def evaluate(
        self,
        day: int,
        compliance_probability: float,
        stress_level: float,
        recent_compliance: bool,
        hrv_trend: float,
        sleep_trend: float,
    ) -> InterventionDecision:
        if recent_compliance:
            self.compliance_streak += 1
            self.non_compliance_streak = 0
        else:
            self.non_compliance_streak += 1
            self.compliance_streak = 0

        should_intervene, priority, reason = self._check_conditions(
            day=day,
            compliance_prob=compliance_probability,
            stress_level=stress_level,
            hrv_trend=hrv_trend,
            sleep_trend=sleep_trend,
        )

        message = None
        if should_intervene:
            message = self._select_message(priority, reason)
            self.last_intervention_day = day
            self.intervention_count += 1
            self._nudge_days.append(day)

        return InterventionDecision(
            triggered=should_intervene,
            message=message,
            intervention_type=self.intervention.intervention_type.value,
            priority=priority,
            reason=reason,
        )

    # --------------------------------------------------------------- internals
    def _check_conditions(
        self,
        day: int,
        compliance_prob: float,
        stress_level: float,
        hrv_trend: float,
        sleep_trend: float,
    ) -> Tuple[bool, Priority, str]:
        params = self.params
        reasons: List[Tuple[str, Priority]] = []

        if compliance_prob < 0.30:
            reasons.append(("very_low_compliance_probability", Priority.HIGH))
        elif compliance_prob < 0.50:
            reasons.append(("low_compliance_probability", Priority.MEDIUM))

        if self.non_compliance_streak >= 3:
            reasons.append(("non_compliance_streak", Priority.HIGH))
        elif self.non_compliance_streak >= 2:
            reasons.append(("consecutive_misses", Priority.MEDIUM))

        if stress_level > params.intervention_urgent_stress:
            reasons.append(("high_stress", Priority.HIGH))
        elif stress_level > params.intervention_elevated_stress:
            reasons.append(("elevated_stress", Priority.MEDIUM))

        if hrv_trend < -5.0:
            reasons.append(("hrv_declining", Priority.MEDIUM))
        if sleep_trend < -1.0:
            reasons.append(("sleep_declining", Priority.MEDIUM))

        priority = max((p for _, p in reasons), default=Priority.LOW)

        days_since_last = day - self.last_intervention_day

        # Anti-fatigue guard: hard cap of nudges per rolling 30 days.  Urgent
        # days are allowed through the *cooldown* but not through the cap.
        window = [d for d in self._nudge_days if day - d < 30]
        if len(window) >= params.intervention_max_per_30_days:
            return False, priority, "nudge_cap_reached"

        # Cooldown: never blocks an urgent (HIGH) day.
        if (
            priority < Priority.HIGH
            and days_since_last < params.intervention_cooldown_days
        ):
            return False, priority, "cooldown"

        if not reasons:
            checkin_gap = max(
                self.intervention.nudge_frequency, params.intervention_checkin_interval
            )
            if day > 3 and days_since_last >= checkin_gap:
                return True, Priority.LOW, "scheduled_checkin"
            return False, Priority.LOW, "no_intervention_needed"

        return True, priority, reasons[0][0]

    def _select_message(self, priority: Priority, reason: str) -> str:
        if "compliance" in reason or "streak" in reason or "misses" in reason:
            category = "warning" if priority >= Priority.HIGH else "reminder"
        elif "stress" in reason:
            category = "warning"
        elif "declining" in reason:
            category = "warning"
        elif "checkin" in reason:
            category = "encouragement" if self.compliance_streak > 3 else "reminder"
        else:
            category = "reminder"

        catalog = MESSAGE_CATALOG.get(
            self.intervention.intervention_type.value, MESSAGE_CATALOG[_FALLBACK_CATEGORY]
        )
        candidates = catalog.get(category) or catalog["reminder"]

        # Never send the same text twice in a row, and prefer text that has not
        # been used recently.
        pool = [m for m in candidates if m != self._last_message] or candidates
        fresh = [m for m in pool if m not in self._recent_messages]
        chosen = self.rng.choice(fresh or pool)
        self._last_message = chosen
        self._recent_messages.append(chosen)
        return chosen

    def get_intervention_count(self) -> int:
        return self.intervention_count
