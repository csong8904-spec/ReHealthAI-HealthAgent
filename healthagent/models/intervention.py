"""Intervention plan data model and the built-in plan registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List


class InterventionType(Enum):
    SLEEP_OPTIMIZATION = "sleep_optimization"
    CARDIO_FITNESS = "cardio_fitness"
    STRESS_MANAGEMENT = "stress_management"
    NUTRITION_PLAN = "nutrition_plan"
    HYBRID = "hybrid"

    @classmethod
    def _missing_(cls, value: object) -> "InterventionType | None":
        """Accept the legacy aliases used by earlier versions."""
        aliases = {
            "cardio_training": cls.CARDIO_FITNESS,
            "stress_reduction": cls.STRESS_MANAGEMENT,
            "holistic_wellness": cls.HYBRID,
            "sleep": cls.SLEEP_OPTIMIZATION,
        }
        if isinstance(value, str):
            return aliases.get(value.strip().lower())
        return None


@dataclass
class InterventionPlan:
    """A behavioural intervention plan.

    Note: ``duration_days`` is a *default*; ``SimulationEngine.run_simulation``
    accepts an explicit ``simulation_days`` that overrides it for that run
    without mutating the plan.
    """

    name: str
    intervention_type: InterventionType
    duration_days: int = 90

    #: How demanding the plan is (0 = trivial, 1 = very demanding).
    intensity: float = 0.5
    difficulty: float = 0.5
    #: Expected effect size when fully adhered to (0..1).
    average_effectiveness: float = 0.6
    #: Minimum days between nudges.
    nudge_frequency: int = 7
    rules: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.intervention_type, str):
            self.intervention_type = InterventionType(self.intervention_type)
        if not 1 <= int(self.duration_days) <= 730:
            raise ValueError(f"duration_days must be within [1, 730], got {self.duration_days}")
        if not 1 <= int(self.nudge_frequency) <= 90:
            raise ValueError(f"nudge_frequency must be within [1, 90], got {self.nudge_frequency}")
        for name in ("intensity", "difficulty", "average_effectiveness"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1], got {value}")
            setattr(self, name, value)
        if self.rules is None:
            self.rules = []
        self.rules = [str(rule) for rule in self.rules]
        self.name = str(self.name)

    @property
    def type_key(self) -> str:
        return self.intervention_type.value


#: Plan registry.  Factories (not shared instances) so that per-run overrides
#: can never leak into another simulation.
PLAN_FACTORIES: Dict[str, Callable[[], InterventionPlan]] = {
    "sleep_optimization": lambda: InterventionPlan(
        name="Sleep Optimization",
        intervention_type=InterventionType.SLEEP_OPTIMIZATION,
        duration_days=90,
        intensity=0.4,
        difficulty=0.35,
        average_effectiveness=0.7,
        nudge_frequency=7,
        rules=[
            "Lights out before 23:00",
            "No screens 30 minutes before bed",
            "Wake at a fixed time, 7 days a week",
        ],
    ),
    "cardio_fitness": lambda: InterventionPlan(
        name="Cardio Fitness",
        intervention_type=InterventionType.CARDIO_FITNESS,
        duration_days=120,
        intensity=0.6,
        difficulty=0.55,
        average_effectiveness=0.65,
        nudge_frequency=5,
        rules=[
            "30-minute brisk walk on 5 days per week",
            "Two 20-minute resistance sessions per week",
            "Take the stairs instead of the lift",
        ],
    ),
    "stress_management": lambda: InterventionPlan(
        name="Stress Management",
        intervention_type=InterventionType.STRESS_MANAGEMENT,
        duration_days=60,
        intensity=0.3,
        difficulty=0.3,
        average_effectiveness=0.6,
        nudge_frequency=4,
        rules=[
            "10-minute mindfulness practice daily",
            "One screen-free evening per week",
            "Three slow-breathing breaks per workday",
        ],
    ),
    "nutrition_plan": lambda: InterventionPlan(
        name="Nutrition Plan",
        intervention_type=InterventionType.NUTRITION_PLAN,
        duration_days=90,
        intensity=0.55,
        difficulty=0.6,
        average_effectiveness=0.55,
        nudge_frequency=7,
        rules=[
            "Low-salt, low-sugar diet",
            "Log every meal for the first 30 days",
            "Two alcohol-free days per week",
        ],
    ),
    "hybrid": lambda: InterventionPlan(
        name="Comprehensive Health Intervention",
        intervention_type=InterventionType.HYBRID,
        duration_days=90,
        intensity=0.5,
        difficulty=0.5,
        average_effectiveness=0.65,
        nudge_frequency=7,
        rules=[
            "30-minute brisk walk daily",
            "Bedtime before 22:30",
            "10-minute daily mindfulness meditation",
            "Low-salt, low-sugar diet",
        ],
    ),
}

#: Legacy alias.
DEFAULT_PLAN = "hybrid"


def available_plans() -> List[str]:
    """Return the names accepted by :func:`get_intervention_plan`."""
    return sorted(PLAN_FACTORIES)


def get_intervention_plan(name: str) -> InterventionPlan:
    """Return a *fresh* plan instance for ``name``.

    Raises:
        ValueError: if the plan name is unknown.
    """
    key = str(name).strip().lower()
    try:
        return PLAN_FACTORIES[key]()
    except KeyError:
        raise ValueError(
            f"unknown intervention plan {name!r}; available plans: {available_plans()}"
        ) from None


def resolve_plan(plan: "str | InterventionPlan | None") -> InterventionPlan:
    """Normalise a plan argument (name, instance, or ``None``)."""
    if plan is None:
        return get_intervention_plan(DEFAULT_PLAN)
    if isinstance(plan, InterventionPlan):
        return plan
    if isinstance(plan, str):
        return get_intervention_plan(plan)
    raise TypeError(
        "intervention_plan must be a plan name (str), an InterventionPlan, or None, "
        f"got {type(plan).__name__}"
    )
