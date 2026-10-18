"""Patient data model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StressLevel(Enum):
    """Self-reported chronic stress level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    def to_baseline(self) -> float:
        """Map the category to the numeric baseline used by the agents."""
        return {"low": 0.25, "medium": 0.50, "high": 0.75}[self.value]

    @classmethod
    def parse(cls, value: "str | StressLevel") -> "StressLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value.strip().lower())
        raise TypeError(f"stress_level must be a str or StressLevel, got {type(value)!r}")


class AgeGroup(Enum):
    YOUNG_ADULT = "young_adult"    # < 30
    MIDDLE_AGED = "middle_aged"    # 30 - 49
    OLDER_ADULT = "older_adult"    # >= 50

    @classmethod
    def from_age(cls, age: int) -> "AgeGroup":
        if age < 30:
            return cls.YOUNG_ADULT
        if age < 50:
            return cls.MIDDLE_AGED
        return cls.OLDER_ADULT


#: Accepted spellings for backward compatibility with earlier examples.
_AGE_GROUP_ALIASES = {
    "young": AgeGroup.YOUNG_ADULT,
    "young_adult": AgeGroup.YOUNG_ADULT,
    "adult": AgeGroup.MIDDLE_AGED,
    "middle_aged": AgeGroup.MIDDLE_AGED,
    "middle-aged": AgeGroup.MIDDLE_AGED,
    "older_adult": AgeGroup.OLDER_ADULT,
    "senior": AgeGroup.OLDER_ADULT,
}


def _clamp01(value: float, name: str) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be within [0, 1], got {value}")
    return value


@dataclass
class PatientProfile:
    """Input characteristics of the simulated patient.

    Only ``age``, ``bmi``, ``sleep_avg_hours`` and ``stress_level`` are
    required in practice; everything else has a documented default.
    """

    name: str = "Patient"

    # demographics
    age: int = 40
    gender: str = "other"
    occupation: str = "office_worker"

    # body metrics
    height: float = 0.0  # metres, optional
    weight: float = 0.0  # kg, optional
    bmi: float = 24.0
    resting_hr: int = 70
    #: Resting HRV baseline in ms.  ``None``/``0`` means "estimate from age".
    hrv_baseline: float | None = 45.0

    # lifestyle
    sleep_avg_hours: float = 7.0
    exercise_per_week: int = 0
    wearable: bool = False

    # psychological state
    stress_level: StressLevel = StressLevel.MEDIUM
    motivation_score: float = 0.5
    habit_strength: float = 0.3
    social_support: float = 0.5

    # clinical context
    primary_issue: str = ""
    age_group: str = ""  # derived from ``age`` when empty

    def __post_init__(self) -> None:
        self.stress_level = StressLevel.parse(self.stress_level)

        if not 10 <= int(self.age) <= 120:
            raise ValueError(f"age must be within [10, 120], got {self.age}")
        if not 10.0 <= float(self.bmi) <= 70.0:
            raise ValueError(f"bmi must be within [10, 70], got {self.bmi}")
        if not 3.0 <= float(self.sleep_avg_hours) <= 14.0:
            raise ValueError(
                f"sleep_avg_hours must be within [3, 14], got {self.sleep_avg_hours}"
            )
        if not 30 <= int(self.resting_hr) <= 130:
            raise ValueError(f"resting_hr must be within [30, 130], got {self.resting_hr}")

        self.motivation_score = _clamp01(self.motivation_score, "motivation_score")
        self.habit_strength = _clamp01(self.habit_strength, "habit_strength")
        self.social_support = _clamp01(self.social_support, "social_support")

        if self.hrv_baseline is not None:
            if float(self.hrv_baseline) == 0.0:
                self.hrv_baseline = None  # 0 / None means "estimate it"
            elif not 5.0 <= float(self.hrv_baseline) <= 200.0:
                raise ValueError(
                    f"hrv_baseline must be within [5, 200] ms, got {self.hrv_baseline}"
                )

        if self.age_group:
            key = str(self.age_group).strip().lower()
            if key not in _AGE_GROUP_ALIASES:
                raise ValueError(
                    f"unknown age_group {self.age_group!r}; "
                    f"expected one of {sorted(_AGE_GROUP_ALIASES)}"
                )
            self.age_group = _AGE_GROUP_ALIASES[key].value
        else:
            self.age_group = AgeGroup.from_age(int(self.age)).value

    @property
    def stress_baseline(self) -> float:
        return self.stress_level.to_baseline()

    @classmethod
    def from_dict(cls, data: "dict") -> "PatientProfile":
        """Build a profile from a loose dictionary, ignoring unknown keys."""
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            raise TypeError(
                "patient must be a dict or PatientProfile, "
                f"got {type(data).__name__}"
            )
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        return cls(**payload)
