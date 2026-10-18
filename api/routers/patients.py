"""Patient profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
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
    name: str = Field(min_length=1, max_length=100, description="Patient name / 患者姓名")
    age: int = Field(ge=10, le=120, description="Age in years / 年龄（岁）")
    gender: str = Field(
        default="unknown", max_length=30, description="Gender / 性别"
    )
    bmi: float = Field(default=22.0, ge=10, le=70, description="Body-mass index / 体质指数")
    stress_level: str = Field(
        default="medium",
        pattern="^(low|medium|high)$",
        description="Chronic stress level / 慢性压力水平（low | medium | high）",
    )
    sleep_hours: float = Field(
        default=7.0, ge=3, le=14, description="Average nightly sleep / 平均睡眠时长（小时）"
    )
    primary_issue: str = Field(
        default="", max_length=500, description="Primary health concern / 主要健康问题"
    )
    medical_history: str = Field(
        default="", max_length=2000, description="Medical history / 既往病史"
    )
    systolic_bp: int = Field(
        default=120, ge=60, le=260, description="Systolic BP (mmHg) / 收缩压"
    )
    diastolic_bp: int = Field(
        default=80, ge=30, le=160, description="Diastolic BP (mmHg) / 舒张压"
    )
    fasting_glucose: float = Field(
        default=5.0, ge=1.0, le=30.0, description="Fasting glucose (mmol/L) / 空腹血糖"
    )


@router.post(
    "",
    summary="Create a patient / 创建患者",
    description="Stores a patient profile and returns its id. / 保存患者档案并返回其 ID。",
    responses={
        200: {"description": "Patient created. / 创建成功。"},
        422: {"description": "Validation error. / 参数校验失败。"},
    },
)
def create_patient(data: PatientCreate):
    return add_patient(**data.model_dump())


@router.get(
    "",
    summary="List patients / 患者列表",
    description="Returns the most recent patients. / 返回最近创建的患者。",
    responses={200: {"description": "List of patients. / 患者列表。"}},
)
def get_all_patients(
    limit: int = Query(
        default=200, ge=1, le=1000, description="Max rows / 最多返回条数"
    ),
):
    return list_patients(limit=limit)


@router.get(
    "/{patient_id}",
    summary="Get a patient / 查询患者",
    description="Returns one patient profile. / 返回单个患者档案。",
    responses={
        200: {"description": "Patient profile. / 患者档案。"},
        404: {"description": "Patient not found. / 患者不存在。"},
    },
)
def get_one_patient(
    patient_id: int = Path(description="Patient id / 患者 ID"),
):
    result = get_patient(patient_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get(
    "/{patient_id}/trend",
    summary="Health trend / 健康趋势",
    description=(
        "Derived 30-day trend from daily records. / 基于每日记录计算的近 30 天趋势。"
    ),
    responses={
        200: {"description": "Trend summary. / 趋势汇总。"},
        404: {"description": "Patient not found. / 患者不存在。"},
    },
)
def get_trend(
    patient_id: int = Path(description="Patient id / 患者 ID"),
):
    if "error" in get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"patient id={patient_id} not found")
    return get_health_trend(patient_id)


@router.get(
    "/{patient_id}/history",
    summary="Simulation history / 模拟历史",
    description=(
        "Stored simulation runs for one patient. / 该患者已保存的模拟运行记录。"
    ),
    responses={200: {"description": "Run history. / 运行历史。"}},
)
def get_history(
    patient_id: int = Path(description="Patient id / 患者 ID"),
    limit: int = Query(
        default=50, ge=1, le=500, description="Max rows / 最多返回条数"
    ),
):
    return get_patient_history(patient_id, limit=limit)
