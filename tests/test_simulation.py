"""End-to-end simulation behaviour."""

from __future__ import annotations

from datetime import datetime

import pytest

from healthagent import SimulationEngine
from healthagent.model_params import ModelParams


def run(patient=None, plan="hybrid", days=90, seed=1, start_date=None):
    return SimulationEngine(seed=seed, offline=True).run_simulation(
        patient=patient,
        intervention_plan=plan,
        simulation_days=days,
        start_date=start_date or datetime(2026, 1, 5),
    )


def test_offline_mode_is_bit_for_bit_deterministic():
    first = run(days=60)
    second = run(days=60)
    assert [d.to_dict() for d in first.trajectory] == [d.to_dict() for d in second.trajectory]
    assert first.reproducible is True
    assert first.mode == "offline"
    assert first.summary() == second.summary()


def test_different_seed_changes_the_trajectory():
    a = run(days=60, seed=1)
    b = run(days=60, seed=2)
    assert [d.hrv for d in a.trajectory] != [d.hrv for d in b.trajectory]


def test_dose_response_adherence_improves_outcomes(
    high_adherence_patient, low_adherence_patient
):
    """The core causal claim: more adherence must mean better simulated outcomes."""
    high = run(high_adherence_patient, days=90)
    low = run(low_adherence_patient, days=90)

    assert high.compliance_rate > 0.80
    assert low.compliance_rate < 0.20
    assert high.hrv_change > low.hrv_change + 3.0
    assert high.sleep_improvement > low.sleep_improvement + 0.2
    assert high.resting_hr_change < low.resting_hr_change - 1.0


def test_high_stress_patient_is_not_structurally_doomed(start_date):
    """Regression: v0.1 drove HRV to the clamp floor for the flagship persona."""
    result = run(days=90)
    assert result.hrv_change > -2.0
    assert result.sleep_improvement > -0.5
    assert min(d.hrv for d in result.trajectory) > result.baseline["hrv"] * 0.5


def test_biomarkers_stay_inside_physiological_bounds(start_date):
    result = run(days=120)
    hrv_floor = result.baseline["hrv"] * 0.40
    hrv_ceiling = result.baseline["hrv"] * 1.80
    for state in result.trajectory:
        assert hrv_floor - 1e-6 <= state.hrv <= hrv_ceiling + 1e-6
        assert 3.5 <= state.sleep_hours <= 10.0
        assert 42 <= state.resting_hr <= 100
        assert 0.0 <= state.stress_level <= 1.0
        assert 0.0 <= state.compliance_score <= 1.0


def test_headline_metrics_use_the_trailing_window(start_date):
    result = run(days=90)
    assert result.metrics_window_days == 14
    window = result.trajectory[-14:]
    expected = sum(d.sleep_hours for d in window) / 14 - result.baseline["sleep_hours"]
    assert result.sleep_improvement == pytest.approx(expected, abs=1e-9)


def test_horizon_validation():
    with pytest.raises(ValueError):
        run(days=0)
    with pytest.raises(ValueError):
        run(days=731)


def test_plan_object_is_not_mutated_by_run():
    from healthagent.models import get_intervention_plan

    plan = get_intervention_plan("hybrid")
    original = plan.duration_days
    SimulationEngine(seed=1, offline=True).run_simulation(
        intervention_plan=plan, simulation_days=10, start_date=datetime(2026, 1, 5)
    )
    assert plan.duration_days == original == 90


def test_weekday_indexing_follows_the_start_date(start_date):
    result = run(days=7)
    assert start_date.weekday() == 0
    assert [d.day_of_week for d in result.trajectory] == [1, 2, 3, 4, 5, 6, 7]


def test_quick_simulation_and_functional_api():
    from healthagent import run_simulation

    engine_result = SimulationEngine(seed=3, offline=True).quick_simulation(days=20)
    function_result = run_simulation(simulation_days=20, seed=3, offline=True)
    assert engine_result.compliance_rate == function_result.compliance_rate


def test_to_dict_contract_used_by_visualizer_and_api():
    payload = run(days=30).to_dict()
    assert set(payload) == {"meta", "summary", "trajectory"}
    assert set(payload["meta"]["baseline"]) == {"sleep_hours", "hrv", "resting_hr", "stress"}
    assert payload["meta"]["patient"]["stress_level"] == "high"
    assert payload["meta"]["intervention"]["type"] == "hybrid"
    assert payload["meta"]["disclaimer"]
    assert set(payload["summary"]) >= {
        "compliance_rate", "average_sleep_hours", "sleep_improvement",
        "hrv_change", "resting_hr_change", "intervention_count", "reproducible",
    }
    assert len(payload["trajectory"]) == 30
    assert payload["trajectory"][0]["day"] == 1


def test_compliance_breakdown_is_consistent():
    result = run(days=90)
    assert result.compliance_rate == pytest.approx(
        result.full_compliance_rate + result.partial_compliance_rate
    )
    for rate in (
        result.compliance_rate,
        result.full_compliance_rate,
        result.partial_compliance_rate,
    ):
        assert 0.0 <= rate <= 1.0
    summary = result.summary()
    assert {"full_compliance_rate", "partial_compliance_rate"} <= set(summary)


def test_custom_model_params_are_honoured():
    from dataclasses import replace

    aggressive = replace(ModelParams(), metric_window_days=7)
    result = SimulationEngine(seed=1, offline=True, params=aggressive).run_simulation(
        simulation_days=30, start_date=datetime(2026, 1, 5)
    )
    assert result.metrics_window_days == 7


def test_unseeded_offline_run_is_reported_as_not_reproducible():
    result = SimulationEngine().run_simulation(
        simulation_days=5, start_date=datetime(2026, 1, 5)
    )
    assert result.mode == "offline"
    assert result.reproducible is False
    assert result.seed is None


class _StubLLM:
    """Minimal stand-in for LLMClient (no network)."""

    available = True
    max_calls = None

    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, prompt, max_tokens=700):
        self.calls += 1
        return {
            "complied": True,
            "compliance_quality": "full",
            "compliance_probability": 0.9,
            "key_factor": "stub",
            "narrative": "stub",
        }


def test_llm_runs_get_a_hard_call_budget_and_are_not_reproducible():
    from healthagent.agents.orchestrator import OrchestratorAgent
    from healthagent.models import PatientProfile, get_intervention_plan

    llm = _StubLLM()
    agent = OrchestratorAgent(
        PatientProfile(age=45),
        get_intervention_plan("hybrid"),
        seed=1,
        llm=llm,
        offline=False,
    )
    result = agent.run(days=4, start_date=datetime(2026, 1, 5))

    assert llm.max_calls == 9, "budget must be horizon + retry slack"
    assert result.mode == "llm"
    assert result.reproducible is False
