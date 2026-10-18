"""Daily self-report endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from api.deps import require_api_key
from healthagent.patient_db.db import add_daily_record, get_daily_records, get_patient

router = APIRouter(dependencies=[Depends(require_api_key)])


class DailyRecordCreate(BaseModel):
    patient_id: int = Field(ge=1, description="Patient id / 患者 ID")
    record_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date YYYY-MM-DD (default: today) / 日期，默认今天",
    )
    systolic_bp: Optional[int] = Field(
        default=None, ge=60, le=260, description="Systolic BP (mmHg) / 收缩压"
    )
    diastolic_bp: Optional[int] = Field(
        default=None, ge=30, le=160, description="Diastolic BP (mmHg) / 舒张压"
    )
    fasting_glucose: Optional[float] = Field(
        default=None, ge=1.0, le=30.0, description="Fasting glucose (mmol/L) / 空腹血糖"
    )
    postprandial_glucose: Optional[float] = Field(
        default=None, ge=1.0, le=40.0, description="Postprandial glucose / 餐后血糖"
    )
    weight: Optional[float] = Field(
        default=None, ge=20.0, le=300.0, description="Weight (kg) / 体重"
    )
    bmi: Optional[float] = Field(
        default=None, ge=10.0, le=70.0, description="Body-mass index / 体质指数"
    )
    steps: Optional[int] = Field(
        default=None, ge=0, le=100_000, description="Step count / 步数"
    )
    exercise_minutes: Optional[int] = Field(
        default=None, ge=0, le=1440, description="Exercise minutes / 运动时长（分钟）"
    )
    mood_score: Optional[int] = Field(
        default=None, ge=0, le=10, description="Mood score 0-10 / 情绪评分"
    )
    sleep_hours: Optional[float] = Field(
        default=None, ge=0, le=24, description="Sleep hours / 睡眠时长（小时）"
    )
    notes: str = Field(default="", max_length=2000, description="Free text / 备注")


@router.post(
    "",
    summary="Add a daily record / 新增每日记录",
    description=(
        "Stores one self-reported measurement day. / 保存一天的自我测量记录。"
    ),
    responses={
        200: {"description": "Record saved. / 记录已保存。"},
        404: {"description": "Patient not found. / 患者不存在。"},
        422: {"description": "Validation error. / 参数校验失败。"},
    },
)
def create_record(data: DailyRecordCreate):
    if "error" in get_patient(data.patient_id):
        raise HTTPException(
            status_code=404, detail=f"patient id={data.patient_id} not found"
        )
    return add_daily_record(**data.model_dump())


@router.get(
    "/{patient_id}",
    summary="List daily records / 每日记录列表",
    description="Returns the most recent records. / 返回最近的记录，按日期倒序。",
    responses={200: {"description": "Daily records. / 每日记录列表。"}},
)
def get_records(
    patient_id: int = Path(description="Patient id / 患者 ID"),
    days: int = Query(
        default=30, ge=1, le=3650, description="How many days back / 回溯天数"
    ),
):
    return get_daily_records(patient_id, days=days)
