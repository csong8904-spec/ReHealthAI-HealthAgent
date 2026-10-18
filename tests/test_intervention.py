"""Nudge policy tests (priority ordering, cooldown, anti-fatigue cap)."""

from __future__ import annotations

from healthagent.agents.intervention_agent import InterventionAgent, Priority
from healthagent.models import InterventionPlan, InterventionType, PatientProfile


def make_agent(seed: int = 1) -> InterventionAgent:
    patient = PatientProfile(age=50, stress_level="high")
    plan = InterventionPlan(
        name="test",
        intervention_type=InterventionType.HYBRID,
        duration_days=90,
        nudge_frequency=7,
    )
    return InterventionAgent(patient, plan, seed=seed)


def evaluate(agent, day, prob=0.2, stress=0.9, recent=False):
    return agent.evaluate(
        day=day,
        compliance_probability=prob,
        stress_level=stress,
        recent_compliance=recent,
        hrv_trend=0.0,
        sleep_trend=0.0,
    )


def test_priority_ordering_is_numeric():
    assert Priority.HIGH > Priority.MEDIUM > Priority.LOW
    assert max(Priority.LOW, Priority.HIGH) is Priority.HIGH


def test_high_severity_day_is_never_downgraded():
    """Regression: ``max("high", "medium") == "medium"`` used to downgrade urgency."""
    agent = make_agent()
    evaluate(agent, day=1)  # first miss -> streak 1
    decision = evaluate(agent, day=30)  # streak 2, very low probability, high stress
    assert agent.non_compliance_streak == 2
    assert decision.priority is Priority.HIGH, decision
    assert decision.triggered is True


def test_urgent_day_bypasses_cooldown():
    agent = make_agent()
    first = evaluate(agent, day=1)
    assert first.triggered
    urgent = evaluate(agent, day=2, prob=0.05, stress=0.95)
    assert urgent.triggered is True
    assert urgent.priority is Priority.HIGH


def test_non_urgent_day_still_respects_cooldown():
    agent = make_agent()
    evaluate(agent, day=1)
    non_urgent = evaluate(agent, day=2, prob=0.45, stress=0.4)
    assert non_urgent.triggered is False
    assert non_urgent.reason == "cooldown"


def test_nudge_cap_prevents_alert_fatigue():
    agent = make_agent()
    days = [
        day
        for day in range(1, 91)
        if evaluate(agent, day=day, prob=0.05, stress=0.95).triggered
    ]
    assert len(days) >= 8
    # Invariant: no rolling 30-day window may contain more than 8 nudges.
    for day in days:
        window = [d for d in days if day - 30 < d <= day]
        assert len(window) <= 8, f"{len(window)} nudges in the 30 days up to day {day}"
    assert agent.intervention_count == len(days)


def test_scheduled_checkin_fires_for_stable_patients():
    agent = make_agent()
    decisions = [
        evaluate(agent, day=day, prob=0.9, stress=0.3, recent=True) for day in range(1, 11)
    ]
    scheduled = [d for d in decisions if d.reason == "scheduled_checkin"]
    assert scheduled, "a stable patient should still get the periodic check-in"
    assert scheduled[0].priority is Priority.LOW


def test_messages_do_not_repeat_back_to_back():
    agent = make_agent()
    messages = []
    for day in range(1, 40):
        decision = evaluate(agent, day=day, prob=0.05, stress=0.95)
        if decision.triggered:
            messages.append(decision.message)
    assert len(messages) >= 5
    repeats = sum(1 for a, b in zip(messages, messages[1:]) if a == b)
    assert repeats <= 1, "the same nudge text must not be sent repeatedly"
    assert len(set(messages)) >= 3, "message variety should be visible"
