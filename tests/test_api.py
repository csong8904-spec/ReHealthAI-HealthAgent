"""API smoke tests (offline mode: no network, no API key)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_meta_endpoints(client):
    assert client.get("/").json()["status"] == "ok"
    assert client.get("/health").json()["status"] == "healthy"


def test_plans_endpoint(client):
    payload = client.get("/api/simulation/plans").json()
    assert "hybrid" in payload["plans"]


def test_run_simulation_offline(client):
    response = client.post(
        "/api/simulation/run",
        json={"days": 5, "offline": True, "seed": 7, "plan": "hybrid"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["mode"] == "offline"
    assert len(payload["trajectory"]) == 5
    assert "summary" in payload


def test_run_simulation_rejects_bad_horizon(client):
    response = client.post("/api/simulation/run", json={"days": 0, "offline": True})
    assert response.status_code == 422


def test_run_simulation_rejects_unknown_plan(client):
    response = client.post(
        "/api/simulation/run", json={"days": 3, "offline": True, "plan": "nope"}
    )
    assert response.status_code == 422


def test_patient_crud(client):
    created = client.post(
        "/api/patients",
        json={"name": "Test Patient", "age": 44, "bmi": 25.0, "stress_level": "high"},
    )
    assert created.status_code == 200, created.text
    patient_id = created.json()["patient_id"]

    listing = client.get("/api/patients").json()
    assert any(item["id"] == patient_id for item in listing)

    detail = client.get(f"/api/patients/{patient_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Test Patient"

    assert client.get("/api/patients/999999").status_code == 404


def test_record_for_unknown_patient_is_rejected(client):
    response = client.post("/api/records", json={"patient_id": 999_999, "steps": 100})
    assert response.status_code == 404


def test_records_and_trend(client):
    patient_id = client.post(
        "/api/patients", json={"name": "Record Holder", "age": 51}
    ).json()["patient_id"]

    created = client.post(
        "/api/records",
        json={
            "patient_id": patient_id,
            "systolic_bp": 118,
            "diastolic_bp": 76,
            "steps": 9000,
            "mood_score": 8,
            "sleep_hours": 7.2,
        },
    )
    assert created.status_code == 200, created.text

    records = client.get(f"/api/records/{patient_id}").json()
    assert len(records) == 1
    assert records[0]["steps"] == 9000

    trend = client.get(f"/api/patients/{patient_id}/trend").json()
    assert trend["record_count"] == 1
    assert trend["blood_pressure"]["status"] == "normal"
    assert trend["activity"]["status"] == "on_target"


def test_trend_returns_404_for_unknown_patient(client):
    assert client.get("/api/patients/999999/trend").status_code == 404


def test_patient_simulation_persists_history(client):
    patient_id = client.post(
        "/api/patients", json={"name": "Simulated", "age": 60, "stress_level": "high"}
    ).json()["patient_id"]

    response = client.post(
        "/api/simulation/patient",
        json={"patient_id": patient_id, "days": 4, "offline": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["meta"]["simulation_days"] == 4

    history = client.get(f"/api/patients/{patient_id}/history").json()
    assert len(history) == 1
    assert history[0]["days"] == 4


def test_openapi_docs_are_bilingual(client):
    """The generated /docs must carry both English and 简体中文 descriptions."""
    schema = client.get("/openapi.json").json()
    description = schema["info"]["description"]
    assert "Research use only" in description
    assert any("\u4e00" <= ch <= "\u9fff" for ch in description)

    tagged = {tag["name"]: tag.get("description", "") for tag in schema.get("tags", [])}
    for name in ("meta", "patients", "records", "simulation"):
        assert name in tagged
        assert any("\u4e00" <= ch <= "\u9fff" for ch in tagged[name])

    patient_fields = schema["components"]["schemas"]["PatientCreate"]["properties"]
    assert "患者姓名" in patient_fields["name"]["description"]
    assert "Patient name" in patient_fields["name"]["description"]


def test_api_key_gate(monkeypatch, client):
    monkeypatch.setenv("REHEALTH_API_KEY", "s3cret")
    assert client.get("/api/patients").status_code == 401
    assert (
        client.get("/api/patients", headers={"X-API-Key": "s3cret"}).status_code == 200
    )
    # meta endpoints stay public for health checks
    assert client.get("/health").status_code == 200
