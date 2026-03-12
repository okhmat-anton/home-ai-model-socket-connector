"""POST /auth/token — issue JWT token."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.auth import create_jwt
from src.config import settings
from src.schemas import TokenRequest, TokenResponse

router = APIRouter()


@router.post("/auth/token", response_model=TokenResponse)
async def issue_token(body: TokenRequest) -> TokenResponse:
    """Issue a JWT token in exchange for valid credentials."""
    # Simple single-user check against USER_API_KEY as password
    if body.password != settings.user_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token, expires_in = create_jwt(subject=body.username)
    return TokenResponse(access_token=token, expires_in=expires_in)
