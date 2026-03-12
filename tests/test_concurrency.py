"""Tests for concurrency limits."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.socketio_handlers import pending_requests


@pytest.mark.asyncio
async def test_concurrent_within_limit(client, auth_headers, connected_model):
    """Requests within MAX_CONCURRENT_REQUESTS should proceed."""

    async def mock_emit(event, data, to=None, namespace=None):
        request_id = data["request_id"]
        fut = pending_requests.get(request_id)
        if fut and not fut.done():
            fut.set_result({
                "request_id": request_id,
                "response": "ok",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })

    with patch("src.main.sio") as mock_sio:
        mock_sio.emit = AsyncMock(side_effect=mock_emit)
        resp = await client.post(
            "/ask",
            json={"prompt": "hello", "model": "test-model"},
            headers=auth_headers,
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_no_model_connected_returns_404(client, auth_headers):
    """If no model is connected, /ask should return 404."""
    resp = await client.post(
        "/ask",
        json={"prompt": "hello"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_prompt_returns_422(client, auth_headers, connected_model):
    """Empty prompt should return 422."""
    resp = await client.post(
        "/ask",
        json={"prompt": "", "model": "test-model"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
