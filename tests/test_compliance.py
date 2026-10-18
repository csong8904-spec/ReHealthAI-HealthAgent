"""Adherence model tests (rule backend + LLM backend contract)."""

from __future__ import annotations

import pytest

from healthagent.agents.compliance_agent import ComplianceAgent
from healthagent.llm import LLMUnavailable
from healthagent.models import InterventionPlan, InterventionType, PatientProfile

RULES = ["walk", "bedtime"]


def make_agent(llm=None, offline: bool = False, seed: int = 1, difficulty: float = 0.5):
    patient = PatientProfile(
        age=34, sleep_avg_hours=5.8, stress_level="medium", motivation_score=0.5
    )
    plan = InterventionPlan(
        name="test",
        intervention_type=InterventionType.HYBRID,
        duration_days=90,
        difficulty=difficulty,
        rules=RULES,
    )
    return ComplianceAgent(patient, plan, seed=seed, llm=llm, offline=offline)


def decide(agent, **overrides):
    payload = dict(
        stress_level=0.5,
        motivation=0.6,
        day_of_week=0,
        sleep_quality=0.6,
        fatigue=0.3,
        previous_compliance=True,
        day=1,
    )
    payload.update(overrides)
    return agent.decide(**payload)


class FakeLLM:
    """Duck-typed stand-in for :class:`healthagent.llm.LLMClient`."""

    def __init__(self, payload=None, fail: bool = False, available: bool = True):
        self.payload = (
            {
                "complied": True,
                "compliance_quality": "full",
                "compliance_probability": 0.82,
                "key_factor": "weekend rest",
                "narrative": "The patient went for a walk.",
            }
            if payload is None
            else payload
        )
        self.fail = fail
        self.available = available
        self.calls = 0
        self.last_prompt = ""

    def complete_json(self, prompt, max_tokens=700):
        self.calls += 1
        self.last_prompt = prompt
        if self.fail:
            raise LLMUnavailable("simulated outage")
        return dict(self.payload)


# ------------------------------------------------------------------ rule mode
def test_rule_mode_is_deterministic():
    first, second = make_agent(seed=7), make_agent(seed=7)
    decisions_a = [decide(first).compliant for _ in range(40)]
    decisions_b = [decide(second).compliant for _ in range(40)]
    assert decisions_a == decisions_b
    assert first.using_llm is False


def test_motivation_increases_adherence_logit():
    agent = make_agent()
    low = agent._logit(0.5, 0.1, 0, 0.6, 0.3, True)
    high = agent._logit(0.5, 0.9, 0, 0.6, 0.3, True)
    assert high > low


def test_stress_lowers_adherence_logit():
    agent = make_agent()
    calm = agent._logit(0.2, 0.6, 0, 0.6, 0.3, True)
    stressed = agent._logit(0.95, 0.6, 0, 0.6, 0.3, True)
    assert calm > stressed


def test_difficulty_lowers_adherence_logit():
    easy = make_agent(difficulty=0.1)._logit(0.5, 0.6, 0, 0.6, 0.3, True)
    hard = make_agent(difficulty=0.95)._logit(0.5, 0.6, 0, 0.6, 0.3, True)
    assert easy > hard


def test_decisions_are_internally_consistent():
    agent = make_agent()
    for _ in range(120):
        decision = decide(agent)
        assert 0.0 <= decision.probability <= 1.0
        if not decision.compliant:
            assert decision.compliance_score == 0.0
        else:
            assert decision.compliance_score in (0.6, 1.0)
        assert decision.source == "rule"


def test_history_is_recorded():
    agent = make_agent()
    for _ in range(5):
        decide(agent)
    assert len(agent.history) == 5


# ------------------------------------------------------------------- LLM mode
def test_llm_success_path_is_used_and_parsed():
    llm = FakeLLM()
    agent = make_agent(llm=llm)
    assert agent.using_llm is True
    decision = decide(agent)
    assert decision.source == "llm"
    assert decision.compliant is True
    assert decision.compliance_score == 1.0
    assert decision.probability == pytest.approx(0.82)
    assert decision.key_factor == "weekend rest"
    assert "compliance_probability" in llm.last_prompt


def test_offline_flag_ignores_the_llm():
    llm = FakeLLM()
    agent = make_agent(llm=llm, offline=True)
    assert agent.using_llm is False
    decide(agent)
    assert llm.calls == 0


def test_llm_without_a_key_is_not_used():
    llm = FakeLLM(available=False)
    agent = make_agent(llm=llm)
    assert agent.using_llm is False
    assert decide(agent).source == "rule"


def test_llm_failure_falls_back_without_crashing():
    llm = FakeLLM(fail=True)
    agent = make_agent(llm=llm)
    decision = decide(agent)
    assert decision.source == "rule"
    assert llm.calls == 1


def test_llm_is_disabled_after_repeated_failures():
    llm = FakeLLM(fail=True)
    agent = make_agent(llm=llm)
    for _ in range(3):
        decide(agent)
    assert agent._llm_disabled is True
    before = llm.calls
    decide(agent)
    assert llm.calls == before, "no further network calls after the circuit opens"


def test_incomplete_llm_payload_degrades_gracefully():
    agent = make_agent(llm=FakeLLM(payload={}))
    decision = decide(agent)
    assert decision.source == "llm"
    assert decision.compliant is False
    assert decision.compliance_score == 0.0
    assert 0.0 <= decision.probability <= 1.0


def test_partial_llm_adherence_is_not_discarded():
    """Regression: a real run returned complied=false + quality=partial for 7 days.

    That is partial adherence (some tasks done) and must score 0.6 rather than 0.
    """
    payload = {
        "complied": False,
        "compliance_quality": "partial",
        "compliance_probability": 0.28,
        "key_factor": "high stress",
        "narrative": "managed only the meditation",
    }
    decision = decide(make_agent(llm=FakeLLM(payload=payload)))
    assert decision.compliant is True
    assert decision.compliance_score == 0.6
    assert decision.source == "llm"


def test_full_llm_adherence_scores_one():
    payload = {"complied": False, "compliance_quality": "full"}
    decision = decide(make_agent(llm=FakeLLM(payload=payload)))
    assert decision.compliant is True
    assert decision.compliance_score == 1.0


def test_none_llm_adherence_scores_zero():
    payload = {"complied": True, "compliance_quality": "none"}
    decision = decide(make_agent(llm=FakeLLM(payload=payload)))
    assert decision.compliant is False
    assert decision.compliance_score == 0.0
