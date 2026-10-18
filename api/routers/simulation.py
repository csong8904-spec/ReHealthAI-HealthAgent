"""Simulation endpoints.

Each simulated day can cost one LLM call (see ``healthagent.llm``), which is why
``days`` is bounded and the work is pushed to a worker thread: the endpoint must
never block the event loop for the length of a 365-day run.
"""

from __future__ import annotations

import functools
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.deps import require_api_key
from healthagent import SimulationEngine, available_plans
from healthagent.patient_db.db import get_patient, save_simulation

router = APIRouter(dependencies=[Depends(require_api_key)])


class SimulationRequest(BaseModel):
    age: int = Field(default=52, ge=10, le=120, description="Age in years / 年龄（岁）")
    stress: Literal["low", "medium", "high"] = Field(
        default="medium", description="Chronic stress level / 慢性压力水平"
    )
    sleep_hours: float = Field(
        default=7.0, ge=3, le=14, description="Average sleep hours / 平均睡眠时长"
    )
    bmi: float = Field(default=22.0, ge=10, le=70, description="Body-mass index / 体质指数")
    days: int = Field(
        default=7, ge=1, le=365, description="Simulation horizon in days / 模拟天数（1–365）"
    )
    plan: str = Field(
        default="hybrid",
        description="Intervention plan name / 干预方案名称（见 /plans）",
    )
    seed: Optional[int] = Field(
        default=None, description="RNG seed; omit for a non-reproducible run / 随机种子，省略则不可复现"
    )
    offline: Optional[bool] = Field(
        default=None,
        description="Force the deterministic rule model / 强制使用确定性规则模型",
    )


class PatientSimulationRequest(BaseModel):
    patient_id: int = Field(ge=1, description="Patient id / 患者 ID")
    days: int = Field(
        default=7, ge=1, le=365, description="Simulation horizon in days / 模拟天数（1–365）"
    )
    plan: str = Field(default="hybrid", description="Intervention plan name / 干预方案名称")
    seed: Optional[int] = Field(default=None, description="RNG seed / 随机种子")
    offline: Optional[bool] = Field(
        default=None, description="Force the deterministic rule model / 强制使用确定性规则模型"
    )


def _validate_plan(plan: str) -> None:
    if plan not in available_plans():
        raise HTTPException(
            status_code=422,
            detail=f"unknown plan {plan!r}; available: {available_plans()}",
        )


@router.get(
    "/plans",
    summary="List intervention plans / 干预方案列表",
    description="Returns the built-in plan names. / 返回内置方案名称列表。",
    responses={200: {"description": "Available plans. / 可用方案。"}},
)
def list_plans() -> dict:
    return {"plans": available_plans()}


@router.post(
    "/run",
    summary="Run a simulation / 运行模拟",
    description=(
        "Runs one simulation from a patient profile. Returns the full trajectory and "
        "a summary; see the README for the schema. / 根据患者画像运行一次模拟，返回完整轨迹"
        "与汇总指标，字段结构见 README。"
    ),
    responses={
        200: {"description": "Simulation result. / 模拟结果。"},
        422: {"description": "Unknown plan or invalid input. / 方案不存在或参数非法。"},
    },
)
async def run_simulation(data: SimulationRequest) -> dict:
    _validate_plan(data.plan)
    engine = SimulationEngine(seed=data.seed, offline=data.offline)
    run = functools.partial(
        engine.run_simulation,
        patient={
            "age": data.age,
            "bmi": data.bmi,
            "sleep_avg_hours": data.sleep_hours,
            "stress_level": data.stress,
        },
        intervention_plan=data.plan,
        simulation_days=data.days,
    )
    result = await run_in_threadpool(run)
    return result.to_dict()


@router.post(
    "/patient",
    summary="Run for a stored patient / 针对已存患者运行",
    description=(
        "Runs a simulation for a stored patient and persists the result. / "
        "为已保存的患者运行模拟，并把结果写入数据库。"
    ),
    responses={
        200: {"description": "Simulation result. / 模拟结果。"},
        404: {"description": "Patient not found. / 患者不存在。"},
        422: {"description": "Unknown plan or invalid input. / 方案不存在或参数非法。"},
    },
)
async def simulate_patient(data: PatientSimulationRequest) -> dict:
    _validate_plan(data.plan)
    patient = get_patient(data.patient_id)
    if "error" in patient:
        raise HTTPException(status_code=404, detail=patient["error"])

    params = {
        "age": patient["age"],
        "stress": patient["stress_level"],
        "sleep_hours": patient["sleep_hours"],
        "bmi": patient["bmi"],
        "days": data.days,
        "primary_issue": patient.get("primary_issue", ""),
    }
    engine = SimulationEngine(seed=data.seed, offline=data.offline)
    run = functools.partial(
        engine.run_simulation,
        patient={
            "age": params["age"],
            "bmi": params["bmi"],
            "sleep_avg_hours": params["sleep_hours"],
            "stress_level": params["stress"],
            "primary_issue": params["primary_issue"],
        },
        intervention_plan=data.plan,
        simulation_days=data.days,
    )
    result = await run_in_threadpool(run)
    payload = result.to_dict()
    save_simulation(data.patient_id, data.days, params, payload)
    return payload
