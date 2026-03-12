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
async def test_models_base_flag(client, auth_headers, connected_model):
    resp = await client.get("/models", headers=auth_headers)
    models = resp.json()["models"]
    assert models[0]["is_base"] is True


@pytest.mark.asyncio
async def test_models_non_base_flag(client, auth_headers):
    await registry.register("other-model", "sid-other", 1000.0)
    resp = await client.get("/models", headers=auth_headers)
    models = resp.json()["models"]
    m = next(m for m in models if m["name"] == "other-model")
    assert m["is_base"] is False
