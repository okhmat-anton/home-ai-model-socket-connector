"""Tests for GET /models."""

import pytest

from src.model_registry import registry


@pytest.mark.asyncio
async def test_models_requires_auth(client):
    resp = await client.get("/models")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_models_empty(client, auth_headers):
    resp = await client.get("/models", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["models"] == []


@pytest.mark.asyncio
async def test_models_with_connected(client, auth_headers, connected_model):
    resp = await client.get("/models", headers=auth_headers)
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert len(models) == 1
    assert models[0]["name"] == "test-model"
    assert models[0]["status"] == "connected"


@pytest.mark.asyncio
async def test_models_default_flag(client, auth_headers, connected_model):
    resp = await client.get("/models", headers=auth_headers)
    models = resp.json()["models"]
    assert models[0]["is_default"] is True


@pytest.mark.asyncio
async def test_models_non_default_flag(client, auth_headers):
    await registry.register("first-model", "sid-first", 1000.0)
    await registry.register("second-model", "sid-other", 1001.0)
    resp = await client.get("/models", headers=auth_headers)
    models = resp.json()["models"]
    assert models[0]["is_default"] is True
    m = next(m for m in models if m["name"] == "second-model")
    assert m["is_default"] is False
