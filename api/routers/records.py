"""Daily self-report endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import require_api_key
from healthagent.patient_db.db import add_daily_record, get_daily_records, get_patient

router = APIRouter(dependencies=[Depends(require_api_key)])


class DailyRecordCreate(BaseModel):
    patient_id: int = Field(ge=1)
    record_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    systolic_bp: Optional[int] = Field(default=None, ge=60, le=260)
    diastolic_bp: Optional[int] = Field(default=None, ge=30, le=160)
    fasting_glucose: Optional[float] = Field(default=None, ge=1.0, le=30.0)
    postprandial_glucose: Optional[float] = Field(default=None, ge=1.0, le=40.0)
    weight: Optional[float] = Field(default=None, ge=20.0, le=300.0)
    bmi: Optional[float] = Field(default=None, ge=10.0, le=70.0)
    steps: Optional[int] = Field(default=None, ge=0, le=100_000)
    exercise_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    mood_score: Optional[int] = Field(default=None, ge=0, le=10)
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    notes: str = Field(default="", max_length=2000)


@router.post("")
def create_record(data: DailyRecordCreate):
    if "error" in get_patient(data.patient_id):
        raise HTTPException(
            status_code=404, detail=f"patient id={data.patient_id} not found"
        )
    return add_daily_record(**data.model_dump())


@router.get("/{patient_id}")
def get_records(patient_id: int, days: int = 30):
    return get_daily_records(patient_id, days=days)
