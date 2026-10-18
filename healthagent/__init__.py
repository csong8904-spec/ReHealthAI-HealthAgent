"""ReHealth HealthAgent - a small, deterministic health-intervention simulator.

Public surface::

    from healthagent import SimulationEngine

    engine = SimulationEngine(seed=42, offline=True)
    result = engine.run_simulation(simulation_days=90)
    print(result.summary())
"""

from healthagent.engine.simulation_engine import SimulationEngine, run_simulation
from healthagent.models import (
    DailyState,
    InterventionPlan,
    InterventionType,
    PatientProfile,
    SimulationResult,
    StressLevel,
    available_plans,
    get_intervention_plan,
)
from healthagent.version import __version__

__all__ = [
    "__version__",
    "SimulationEngine",
    "run_simulation",
    "PatientProfile",
    "StressLevel",
    "InterventionPlan",
    "InterventionType",
    "DailyState",
    "SimulationResult",
    "available_plans",
    "get_intervention_plan",
]
