"""FastAPI application factory.

Run from the repository root::

    uvicorn api.main:app --reload

Environment:
    REHEALTH_API_KEY      when set, every request must send ``X-API-Key``.
    REHEALTH_CORS_ORIGINS comma-separated allow-list (default: local dev URLs).
    REHEALTH_DB_PATH      SQLite file for patient data.

The generated OpenAPI documentation (``/docs``) is bilingual: every description
and field hint is written in English first and 简体中文 second.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import patients, records, simulation
from healthagent.version import __version__

_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"

_DESCRIPTION = (
    "Patient records and behavioural health-intervention simulations. "
    "Research use only - not a medical device and not clinical advice.\n\n"
    "患者档案与行为健康干预模拟。仅供研究使用——本服务不是医疗器械，也不构成任何临床建议。\n\n"
    "All endpoints exchange JSON. When `REHEALTH_API_KEY` is set, every `/api/*` "
    "route requires the `X-API-Key` header.\n\n"
    "所有接口均使用 JSON。当设置了 `REHEALTH_API_KEY` 时，所有 `/api/*` 路由都需要 "
    "`X-API-Key` 请求头。"
)

_OPENAPI_TAGS = [
    {
        "name": "meta",
        "description": "Liveness and service metadata. / 存活检查与服务元信息。",
    },
    {
        "name": "patients",
        "description": "Patient profiles and derived health trends. / 患者档案与健康趋势。",
    },
    {
        "name": "records",
        "description": "Daily self-reported measurements. / 每日自报测量记录。",
    },
    {
        "name": "simulation",
        "description": "Behavioural intervention simulations. / 行为干预模拟。",
    },
]


def create_app() -> FastAPI:
    application = FastAPI(
        title="ReHealth HealthAgent API",
        description=_DESCRIPTION,
        version=__version__,
        openapi_tags=_OPENAPI_TAGS,
        contact={"name": "ReHealth AI", "url": "https://github.com/csong8904-spec/ReHealthAI-HealthAgent"},
        license_info={"name": "Apache-2.0"},
    )

    raw_origins = os.getenv("REHEALTH_CORS_ORIGINS", _DEFAULT_ORIGINS)
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    allow_all = origins == ["*"]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(
        patients.router, prefix="/api/patients", tags=["patients"]
    )
    application.include_router(records.router, prefix="/api/records", tags=["records"])
    application.include_router(
        simulation.router, prefix="/api/simulation", tags=["simulation"]
    )

    @application.get(
        "/",
        tags=["meta"],
        summary="Service metadata / 服务元信息",
        description="Returns the service name and version. / 返回服务名称与版本号。",
        responses={200: {"description": "Service metadata. / 服务元信息。"}},
    )
    def root() -> dict:
        return {"status": "ok", "service": "rehealth-healthagent", "version": __version__}

    @application.get(
        "/health",
        tags=["meta"],
        summary="Liveness probe / 健康检查",
        description="Returns 200 while the process is alive. / 进程存活时返回 200。",
        responses={200: {"description": "Service is healthy. / 服务健康。"}},
    )
    def health() -> dict:
        return {"status": "healthy"}

    return application


app = create_app()
