"""GET /models — list connected models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.auth import require_user_auth
from src.config import settings
from src.model_registry import registry
from src.schemas import ModelInfo, ModelsResponse

router = APIRouter()


@router.get("/models", response_model=ModelsResponse)
async def list_models(_user: str = Depends(require_user_auth)) -> ModelsResponse:
    names = await registry.list_names()
    models = [
        ModelInfo(name=n, status="connected", is_base=(n == settings.base_model))
        for n in names
    ]
    return ModelsResponse(models=models)
