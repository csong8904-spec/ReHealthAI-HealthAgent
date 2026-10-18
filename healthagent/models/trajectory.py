"""Simulation output data structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

DISCLAIMER = "Research use only; not medical advice."


@dataclass
class DailyState:
    """One simulated day."""

    day: int
    day_of_week: int  # 1 = Monday ... 7 = Sunday
    date: datetime

    emotion_state: str
    stress_level: float
    motivation: float

    compliance: bool
    compliance_score: float

    sleep_hours: float
    sleep_quality: float
    hrv: float
    resting_hr: int

    intervention_triggered: bool = False
    intervention_message: Optional[str] = None

    narrative: str = ""
    key_factor: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        data["sleep_hours"] = round(self.sleep_hours, 2)
        data["sleep_quality"] = round(self.sleep_quality, 3)
        data["hrv"] = round(self.hrv, 2)
        data["stress_level"] = round(self.stress_level, 3)
        data["motivation"] = round(self.motivation, 3)
        data["compliance_score"] = round(self.compliance_score, 3)
        return data


@dataclass
class SimulationResult:
    """Aggregated output of one simulation run."""

    trajectory: List[DailyState] = field(default_factory=list)

    compliance_rate: float = 0.0
    #: Share of days with full adherence (compliance_score == 1.0).
    full_compliance_rate: float = 0.0
    #: Share of days with partial adherence (0 < compliance_score < 1.0).
    partial_compliance_rate: float = 0.0
    average_sleep_hours: float = 0.0
    average_stress: float = 0.0
    sleep_improvement: float = 0.0
    hrv_change: float = 0.0
    resting_hr_change: float = 0.0
    intervention_count: int = 0

    simulation_days: int = 0
    metrics_window_days: int = 14
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    mode: str = "offline"  # "offline" | "llm"
    seed: Optional[int] = None
    #: True only for a fully seeded offline run (see OrchestratorAgent.run).
    reproducible: bool = False

    patient: Dict[str, Any] = field(default_factory=dict)
    intervention: Dict[str, Any] = field(default_factory=dict)
    baseline: Dict[str, Any] = field(default_factory=dict)
    version: str = "0.2.0"

    # ------------------------------------------------------------------ views
    @property
    def final_sleep_hours(self) -> float:
        return self.trajectory[-1].sleep_hours if self.trajectory else 0.0

    @property
    def final_hrv(self) -> float:
        return self.trajectory[-1].hrv if self.trajectory else 0.0

    @property
    def final_resting_hr(self) -> int:
        return self.trajectory[-1].resting_hr if self.trajectory else 0

    def summary(self) -> Dict[str, Any]:
        return {
            "compliance_rate": round(self.compliance_rate, 3),
            "full_compliance_rate": round(self.full_compliance_rate, 3),
            "partial_compliance_rate": round(self.partial_compliance_rate, 3),
            "average_sleep_hours": round(self.average_sleep_hours, 2),
            "sleep_improvement": round(self.sleep_improvement, 2),
            "hrv_change": round(self.hrv_change, 2),
            "resting_hr_change": round(self.resting_hr_change, 2),
            "intervention_count": self.intervention_count,
            "average_stress": round(self.average_stress, 3),
            "final_sleep_hours": round(self.final_sleep_hours, 2),
            "final_hrv": round(self.final_hrv, 2),
            "final_resting_hr": self.final_resting_hr,
            "reproducible": self.reproducible,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable form consumed by ``simulate.py`` and ``visualize.py``."""
        return {
            "meta": {
                "version": self.version,
                "mode": self.mode,
                "seed": self.seed,
                "simulation_days": self.simulation_days,
                "metrics_window_days": self.metrics_window_days,
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "end_date": self.end_date.isoformat() if self.end_date else None,
                "patient": self.patient,
                "intervention": self.intervention,
                "baseline": self.baseline,
                "disclaimer": DISCLAIMER,
            },
            "summary": self.summary(),
            "trajectory": [day.to_dict() for day in self.trajectory],
        }
