"""Model and plan-registry tests."""

from __future__ import annotations

import pytest

from healthagent.models import (
    InterventionPlan,
    InterventionType,
    PatientProfile,
    StressLevel,
    available_plans,
    get_intervention_plan,
)
from healthagent.models.patient_profile import AgeGroup


def test_stress_level_parses_strings_case_insensitively():
    profile = PatientProfile(stress_level="HIGH")
    assert profile.stress_level is StressLevel.HIGH
    assert profile.stress_baseline == pytest.approx(0.75)


def test_age_group_is_derived_and_aliases_accepted():
    assert PatientProfile(age=22).age_group == AgeGroup.YOUNG_ADULT.value
    assert PatientProfile(age=45).age_group == AgeGroup.MIDDLE_AGED.value
    assert PatientProfile(age=61).age_group == AgeGroup.OLDER_ADULT.value
    assert PatientProfile(age=61, age_group="senior").age_group == AgeGroup.OLDER_ADULT.value


def test_patient_from_dict_ignores_unknown_keys_and_keeps_known_ones():
    profile = PatientProfile.from_dict(
        {"age": 50, "bmi": 26, "sleep_avg_hours": 6.0, "stress_level": "high",
         "occupation": "teacher", "not_a_field": 1}
    )
    assert profile.occupation == "teacher"
    assert profile.stress_level is StressLevel.HIGH


@pytest.mark.parametrize(
    "payload",
    [
        {"age": 5},
        {"age": 40, "bmi": 5},
        {"age": 40, "sleep_avg_hours": 20},
        {"age": 40, "resting_hr": 200},
        {"age": 40, "motivation_score": 2.0},
        {"age": 40, "hrv_baseline": -3},
        {"age": 40, "stress_level": "extreme"},
    ],
)
def test_patient_validation_rejects_impossible_values(payload):
    with pytest.raises((ValueError, TypeError)):
        PatientProfile(**payload)


def test_unknown_patient_type_is_rejected():
    with pytest.raises(TypeError):
        PatientProfile.from_dict(["not", "a", "dict"])


def test_all_builtin_plans_resolve_to_fresh_instances():
    names = available_plans()
    assert "hybrid" in names and "sleep_optimization" in names
    first = get_intervention_plan("hybrid")
    second = get_intervention_plan("hybrid")
    assert first is not second
    first.duration_days = 3
    assert get_intervention_plan("hybrid").duration_days == 90


def test_plan_name_is_case_insensitive_and_unknown_raises():
    assert get_intervention_plan("HYBRID").intervention_type is InterventionType.HYBRID
    with pytest.raises(ValueError, match="available plans"):
        get_intervention_plan("does_not_exist")


def test_legacy_type_aliases_still_parse():
    assert InterventionType("cardio_training") is InterventionType.CARDIO_FITNESS
    assert InterventionType("stress_reduction") is InterventionType.STRESS_MANAGEMENT
    assert InterventionType("holistic_wellness") is InterventionType.HYBRID


def test_plan_validation():
    with pytest.raises(ValueError):
        InterventionPlan(name="x", intervention_type=InterventionType.HYBRID, duration_days=0)
    with pytest.raises(ValueError):
        InterventionPlan(
            name="x", intervention_type=InterventionType.HYBRID, difficulty=1.5
        )
