"""Pydantic schemas for requests and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Ask ──────────────────────────────────────────────────────────────────────

class InferenceParameters(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    model: str | None = None
    stream: bool = False
    parameters: InferenceParameters | None = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AskResponse(BaseModel):
    response: str
    model: str
    usage: UsageInfo
    elapsed_seconds: float


# ── Models ───────────────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    name: str
    status: str = "connected"
    is_default: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


# ── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    uptime_seconds: float
    connected_models: list[str]


# ── Auth ─────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ── SSE chunk ────────────────────────────────────────────────────────────────

class StreamChunk(BaseModel):
    token: str
    done: bool
    usage: UsageInfo | None = None
    elapsed_seconds: float | None = None
