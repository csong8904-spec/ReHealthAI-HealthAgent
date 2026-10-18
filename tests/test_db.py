"""SQLite persistence tests."""

from __future__ import annotations

from pathlib import Path

from healthagent.patient_db import db


def test_db_path_honours_environment(monkeypatch, tmp_path):
    target = tmp_path / "nested" / "custom.db"
    monkeypatch.setenv("REHEALTH_DB_PATH", str(target))
    assert db.db_path() == target


def test_patient_roundtrip():
    created = db.add_patient("Alice", 42, bmi=23.5, stress_level="high")
    patient_id = created["patient_id"]

    fetched = db.get_patient(patient_id)
    assert fetched["name"] == "Alice"
    assert fetched["stress_level"] == "high"
    assert fetched["bmi"] == 23.5

    assert any(item["id"] == patient_id for item in db.list_patients())
    assert "error" in db.get_patient(999_999)


def test_daily_records_and_trend():
    patient_id = db.add_patient("Bob", 55)["patient_id"]
    db.add_daily_record(
        patient_id,
        record_date="2026-01-01",
        systolic_bp=118,
        diastolic_bp=76,
        fasting_glucose=5.4,
        weight=82.0,
        steps=9000,
        mood_score=8,
        sleep_hours=7.1,
    )
    db.add_daily_record(
        patient_id,
        record_date="2026-01-02",
        systolic_bp=122,
        diastolic_bp=78,
        fasting_glucose=5.6,
        weight=81.5,
        steps=7000,
        mood_score=6,
        sleep_hours=6.4,
    )

    records = db.get_daily_records(patient_id)
    assert len(records) == 2
    assert records[0]["record_date"] == "2026-01-02"  # newest first

    trend = db.get_health_trend(patient_id)
    assert trend["record_count"] == 2
    assert trend["blood_pressure"]["avg_systolic"] > 118
    assert trend["activity"]["status"] == "on_target"
    assert trend["glucose"]["status"] == "normal"
    assert trend["mood"]["status"] == "fair"
    assert trend["weight"]["change"] == -0.5


def test_trend_for_patient_without_records():
    patient_id = db.add_patient("Empty", 30)["patient_id"]
    assert "error" in db.get_health_trend(patient_id)


def test_simulation_history_roundtrip():
    patient_id = db.add_patient("Carol", 47)["patient_id"]
    payload = {
        "meta": {"mode": "offline", "seed": 3},
        "summary": {"compliance_rate": 0.5},
        "trajectory": [],
    }
    db.save_simulation(patient_id, 30, {"days": 30}, payload)

    history = db.get_patient_history(patient_id)
    assert len(history) == 1
    assert history[0]["days"] == 30
    assert history[0]["mode"] == "offline"
    assert history[0]["seed"] == 3
    assert history[0]["result"]["summary"]["compliance_rate"] == 0.5


def test_database_file_is_created_under_the_configured_path():
    assert Path(db.init_db()).exists()
