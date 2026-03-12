"""Tests for POST /ask."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.model_registry import registry
from src.socketio_handlers import pending_requests


@pytest.mark.asyncio
async def test_ask_no_model_connected(client, auth_headers):
    resp = await client.post("/ask", json={"prompt": "hello"}, headers=auth_headers)
    assert resp.status_code == 404
    assert "no models connected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ask_nonexistent_model(client, auth_headers, connected_model):
    resp = await client.post(
        "/ask",
        json={"prompt": "hello", "model": "nonexistent"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ask_empty_prompt(client, auth_headers, connected_model):
    resp = await client.post("/ask", json={"prompt": ""}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ask_valid_prompt(client, auth_headers, connected_model):
    """Test that a valid ask request emits to Socket.IO and returns response."""
    response_data = {
        "request_id": None,  # will be set dynamically
        "response": "Test response from model",
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
    }

    original_emit = None

    async def mock_emit(event, data, to=None, namespace=None):
        # Simulate model responding
        request_id = data["request_id"]
        response_data["request_id"] = request_id
        # Resolve the pending future
        fut = pending_requests.get(request_id)
        if fut and not fut.done():
            fut.set_result(response_data)

    with patch("src.main.sio") as mock_sio:
        mock_sio.emit = AsyncMock(side_effect=mock_emit)
        resp = await client.post(
            "/ask",
            json={"prompt": "hello", "model": "test-model"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["response"] == "Test response from model"
    assert data["model"] == "test-model"
    assert data["usage"]["total_tokens"] == 15
    assert data["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_ask_uses_first_connected_model(client, auth_headers, connected_model):
    """Without specifying model, should use the first connected model."""
    async def mock_emit(event, data, to=None, namespace=None):
        request_id = data["request_id"]
        fut = pending_requests.get(request_id)
        if fut and not fut.done():
            fut.set_result({"request_id": request_id, "response": "ok", "usage": {}})

    with patch("src.main.sio") as mock_sio:
        mock_sio.emit = AsyncMock(side_effect=mock_emit)
        resp = await client.post("/ask", json={"prompt": "hello"}, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["model"] == "test-model"


@pytest.mark.asyncio
async def test_ask_timeout(client, auth_headers, connected_model):
    """Should return 408 on timeout."""
    with patch("src.main.sio") as mock_sio:
        mock_sio.emit = AsyncMock()  # Does not resolve the future
        with patch("src.routes.ask.settings") as mock_settings:
            mock_settings.request_timeout = 0.1
            mock_settings.max_concurrent_requests = 10
            resp = await client.post("/ask", json={"prompt": "hello"}, headers=auth_headers)

    assert resp.status_code == 408
