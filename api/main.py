"""FastAPI application factory.

Run from the repository root::

    uvicorn api.main:app --reload

Environment:
    REHEALTH_API_KEY     when set, every request must send ``X-API-Key``.
    REHEALTH_CORS_ORIGINS comma-separated allow-list (default: local dev URLs).
    REHEALTH_DB_PATH     SQLite file for patient data.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import patients, records, simulation
from healthagent.version import __version__

_DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"


def create_app() -> FastAPI:
    application = FastAPI(
        title="ReHealth HealthAgent API",
        description=(
            "Patient records and behavioural health-intervention simulations. "
            "Research use only - not a medical device and not clinical advice."
        ),
        version=__version__,
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

    application.include_router(patients.router, prefix="/api/patients", tags=["patients"])
    application.include_router(records.router, prefix="/api/records", tags=["records"])
    application.include_router(
        simulation.router, prefix="/api/simulation", tags=["simulation"]
    )

    @application.get("/", tags=["meta"])
    def root() -> dict:
        return {"status": "ok", "service": "rehealth-healthagent", "version": __version__}

    @application.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "healthy"}

    return application


app = create_app()
