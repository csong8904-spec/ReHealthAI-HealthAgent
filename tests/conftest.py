"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Never touch the developer's env, API key or real database."""
    monkeypatch.setenv("REHEALTH_OFFLINE", "1")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("REHEALTH_DB_PATH", str(tmp_path / "patients.db"))
    monkeypatch.delenv("REHEALTH_API_KEY", raising=False)


@pytest.fixture
def start_date() -> datetime:
    return datetime(2026, 1, 5)  # a Monday


@pytest.fixture
def high_adherence_patient() -> dict:
    return {
        "age": 45,
        "bmi": 24.0,
        "resting_hr": 68,
        "hrv_baseline": 45.0,
        "sleep_avg_hours": 6.4,
        "stress_level": "medium",
        "motivation_score": 1.0,
        "habit_strength": 1.0,
        "social_support": 1.0,
    }


@pytest.fixture
def low_adherence_patient() -> dict:
    return {
        "age": 45,
        "bmi": 24.0,
        "resting_hr": 68,
        "hrv_baseline": 45.0,
        "sleep_avg_hours": 6.4,
        "stress_level": "high",
        "motivation_score": 0.0,
        "habit_strength": 0.0,
        "social_support": 0.0,
    }
