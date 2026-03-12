"""Tests for Socket.IO model connection and inference flow."""

from __future__ import annotations

import pytest

from src.model_registry import registry
from src.socketio_handlers import InferenceError, ModelNamespace, pending_requests


@pytest.mark.asyncio
async def test_connect_valid_key():
    ns = ModelNamespace()
    result = await ns.on_connect("sid-1", {}, auth={"api_key": "test-model-key", "model_name": "llama3"})
    assert result is True
    assert await registry.is_connected("llama3")


@pytest.mark.asyncio
async def test_connect_invalid_key():
    ns = ModelNamespace()
    result = await ns.on_connect("sid-1", {}, auth={"api_key": "wrong-key", "model_name": "llama3"})
    assert result is False
    assert not await registry.is_connected("llama3")


@pytest.mark.asyncio
async def test_connect_no_auth():
    ns = ModelNamespace()
    result = await ns.on_connect("sid-1", {}, auth=None)
    assert result is False


@pytest.mark.asyncio
async def test_connect_no_model_name():
    ns = ModelNamespace()
    result = await ns.on_connect("sid-1", {}, auth={"api_key": "test-model-key", "model_name": ""})
    assert result is False


@pytest.mark.asyncio
async def test_disconnect_removes_model():
    ns = ModelNamespace()
    await ns.on_connect("sid-1", {}, auth={"api_key": "test-model-key", "model_name": "llama3"})
    assert await registry.is_connected("llama3")

    await ns.on_disconnect("sid-1")
    assert not await registry.is_connected("llama3")


@pytest.mark.asyncio
async def test_inference_response_resolves_future():
    import asyncio

    ns = ModelNamespace()
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    pending_requests["req-1"] = fut

    await ns.on_inference_response("sid-1", {
        "request_id": "req-1",
        "response": "Hello!",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    })

    assert fut.done()
    result = fut.result()
    assert result["response"] == "Hello!"


@pytest.mark.asyncio
async def test_inference_error_rejects_future():
    import asyncio

    ns = ModelNamespace()
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    pending_requests["req-2"] = fut

    await ns.on_inference_error("sid-1", {
        "request_id": "req-2",
        "error": "OOM",
        "code": "OUT_OF_MEMORY",
    })

    assert fut.done()
    with pytest.raises(InferenceError):
        fut.result()
