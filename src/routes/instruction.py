"""GET /instruction — human/AI-readable instruction for using the service."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from src.config import settings
from src.model_registry import registry

router = APIRouter()

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "instruction.txt"


@router.get("/instruction", response_class=PlainTextResponse)
async def get_instruction() -> str:
    """Return usage instruction with live values substituted."""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    models = await registry.list_names()
    models_str = ", ".join(models) if models else "(none connected)"

    return template.format(
        server_ip=settings.host if settings.host != "0.0.0.0" else "<server_ip>",
        port=settings.port,
        proxy_port=settings.proxy_port,
        base_model=settings.base_model,
        connected_models=models_str,
    )
