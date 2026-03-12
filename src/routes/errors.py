"""GET /errors — query error log by request_id or event type."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.auth import require_user_auth
from src.error_store import error_store

router = APIRouter()


@router.get("/errors")
async def get_errors(
    _user: str = Depends(require_user_auth),
    request_id: str | None = Query(None, description="Filter by request_id"),
    event: str | None = Query(None, description="Filter by event type (e.g. ask_timeout, auth_invalid)"),
    limit: int = Query(50, ge=1, le=500, description="Max entries to return"),
):
    """Return recent errors, optionally filtered by request_id or event type."""
    if request_id:
        entries = error_store.get_by_request_id(request_id)
    elif event:
        entries = error_store.get_by_event(event)
    else:
        entries = error_store.get_recent(limit)

    return {"total": len(entries), "errors": entries[:limit]}
