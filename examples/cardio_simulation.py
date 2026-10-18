#!/usr/bin/env python3
"""Cardio fitness simulation example.

Runs a 120-day, fully deterministic offline simulation (no LLM calls and no
API key required) and prints cardiovascular outcomes.

Usage:
    python examples/cardio_simulation.py

Research use only; not medical advice.
"""

from __future__ import annotations

import os
import sys

# Make "python examples/cardio_simulation.py" work from the repository root.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from healthagent import SimulationEngine

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
PATIENT = {
    "age": 42,
    "bmi": 27.5,
    "sleep_avg_hours": 6.5,
    "stress_level": "medium",
}


def weekday_compliance(trajectory):
    """Return (weekday name, compliant days, total days) for day_of_week 1-7."""
    totals = {day: 0 for day in range(1, 8)}
    compliant = {day: 0 for day in range(1, 8)}
    for state in trajectory:
        index = state.day_of_week
        totals[index] += 1
        if state.compliance:
            compliant[index] += 1
    return [(WEEKDAYS[index - 1], compliant[index], totals[index]) for index in range(1, 8)]


def main() -> None:
    print("=" * 64)
    print("  CARDIO FITNESS SIMULATION (offline, deterministic)")
    print("=" * 64)
    print(f"  Patient: {PATIENT['age']} y/o, BMI {PATIENT['bmi']}, "
          f"baseline sleep {PATIENT['sleep_avg_hours']} h, stress {PATIENT['stress_level']}")

    engine = SimulationEngine(seed=123, offline=True)
    result = engine.run_simulation(
        patient=PATIENT,
        intervention_plan="cardio_fitness",
        simulation_days=120,
    )

    trajectory = result.trajectory
    first_hrv = trajectory[0].hrv
    final_hrv = trajectory[-1].hrv
    first_hr = trajectory[0].resting_hr
    final_hr = trajectory[-1].resting_hr

    print("-" * 64)
    print(f"  Simulated days:        {result.simulation_days}")
    print(f"  Compliance rate:       {result.compliance_rate:.1%}")
    print(f"  Interventions sent:    {result.intervention_count}")
    print(f"  Resting HR start/end:  {first_hr} -> {final_hr} bpm "
          f"({result.resting_hr_change:+.1f} bpm vs baseline)")
    print(f"  HRV start/end:         {first_hrv:.1f} -> {final_hrv:.1f} ms "
          f"({result.hrv_change:+.2f} ms vs baseline)")
    print(f"  Average sleep:         {result.average_sleep_hours:.2f} h")
    print(f"  Sleep improvement:     {result.sleep_improvement:+.2f} h")

    print("-" * 64)
    print("  Compliance by weekday:")
    for name, compliant, total in weekday_compliance(trajectory):
        rate = compliant / total if total else 0.0
        print(f"    {name:<9} {rate:6.1%}  ({compliant}/{total} days)")

    print("=" * 64)
    print("  Research use only; not medical advice.")


if __name__ == "__main__":
    main()
