"""Authentication helpers: API-key verification + optional JWT."""

from __future__ import annotations

import time
from typing import Annotated

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings
from src.error_store import error_store

logger = structlog.get_logger()
_bearer = HTTPBearer(auto_error=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

def create_jwt(subject: str) -> tuple[str, int]:
    """Create a JWT token. Returns (token, expires_in)."""
    exp = int(time.time()) + settings.token_expire_seconds
    payload = {"sub": subject, "exp": exp}
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, settings.token_expire_seconds


def _verify_jwt(token: str) -> str | None:
    """Return subject if token valid, else None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ── FastAPI dependencies ─────────────────────────────────────────────────────

async def require_user_auth(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """Verify user API key or JWT token. Returns user identifier."""
    if credentials is None:
        client_ip = request.client.host if request.client else "unknown"
        error_store.add("auth", "auth_missing", "Missing authorization header", client_ip=client_ip, path=request.url.path)
        logger.warning("auth_missing", client_ip=client_ip, path=request.url.path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    token = credentials.credentials

    # Direct API-key match
    if token == settings.user_api_key:
        return "api-key-user"

    # Try JWT
    subject = _verify_jwt(token)
    if subject:
        return subject

    client_ip = request.client.host if request.client else "unknown"
    error_store.add("auth", "auth_invalid", "Invalid or expired token", client_ip=client_ip, path=request.url.path)
    logger.warning("auth_invalid", client_ip=client_ip, path=request.url.path)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
