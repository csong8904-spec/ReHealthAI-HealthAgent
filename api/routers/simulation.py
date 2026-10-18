"""Simulation endpoints.

Each simulated day can cost one LLM call (see ``healthagent.llm``), which is why
``days`` is bounded and the work is pushed to a worker thread: the endpoint must
never block the event loop for the length of a 365-day run.
"""

from __future__ import annotations

import functools
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.deps import require_api_key
from healthagent import SimulationEngine, available_plans
from healthagent.patient_db.db import get_patient, save_simulation

router = APIRouter(dependencies=[Depends(require_api_key)])


class SimulationRequest(BaseModel):
    age: int = Field(default=52, ge=10, le=120)
    stress: Literal["low", "medium", "high"] = "medium"
    sleep_hours: float = Field(default=7.0, ge=3, le=14)
    bmi: float = Field(default=22.0, ge=10, le=70)
    days: int = Field(default=7, ge=1, le=365)
    plan: str = "hybrid"
    seed: Optional[int] = None
    offline: Optional[bool] = None


class PatientSimulationRequest(BaseModel):
    patient_id: int = Field(ge=1)
    days: int = Field(default=7, ge=1, le=365)
    plan: str = "hybrid"
    seed: Optional[int] = None
    offline: Optional[bool] = None


def _validate_plan(plan: str) -> None:
    if plan not in available_plans():
        raise HTTPException(
            status_code=422,
            detail=f"unknown plan {plan!r}; available: {available_plans()}",
        )


@router.get("/plans")
def list_plans() -> dict:
    return {"plans": available_plans()}


@router.post("/run")
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


@router.post("/patient")
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
