"""GET /health — server health check."""

from __future__ import annotations

import time

from fastapi import APIRouter

from src.model_registry import registry
from src.schemas import HealthResponse

router = APIRouter()

_start_time = time.time()
VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    models = await registry.list_names()
    return HealthResponse(
        status="ok",
        version=VERSION,
        uptime_seconds=round(time.time() - _start_time, 1),
        connected_models=models,
    )
