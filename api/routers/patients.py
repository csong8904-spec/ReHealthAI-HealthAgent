"""Patient profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import require_api_key
from healthagent.patient_db.db import (
    add_patient,
    get_health_trend,
    get_patient,
    get_patient_history,
    list_patients,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=10, le=120)
    gender: str = Field(default="unknown", max_length=30)
    bmi: float = Field(default=22.0, ge=10, le=70)
    stress_level: str = Field(default="medium", pattern="^(low|medium|high)$")
    sleep_hours: float = Field(default=7.0, ge=3, le=14)
    primary_issue: str = Field(default="", max_length=500)
    medical_history: str = Field(default="", max_length=2000)
    systolic_bp: int = Field(default=120, ge=60, le=260)
    diastolic_bp: int = Field(default=80, ge=30, le=160)
    fasting_glucose: float = Field(default=5.0, ge=1.0, le=30.0)


@router.post("")
def create_patient(data: PatientCreate):
    return add_patient(**data.model_dump())


@router.get("")
def get_all_patients(limit: int = 200):
    return list_patients(limit=limit)


@router.get("/{patient_id}")
def get_one_patient(patient_id: int):
    result = get_patient(patient_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{patient_id}/trend")
def get_trend(patient_id: int):
    if "error" in get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"patient id={patient_id} not found")
    return get_health_trend(patient_id)


@router.get("/{patient_id}/history")
def get_history(patient_id: int, limit: int = 50):
    return get_patient_history(patient_id, limit=limit)
