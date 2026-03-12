"""Tests for POST /auth/token."""

import pytest


@pytest.mark.asyncio
async def test_auth_valid_credentials(client):
    resp = await client.post("/auth/token", json={"username": "admin", "password": "test-user-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_auth_invalid_credentials(client):
    resp = await client.post("/auth/token", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ask_without_token(client):
    resp = await client.post("/ask", json={"prompt": "hello"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ask_with_jwt_token(client):
    # Get token
    resp = await client.post("/auth/token", json={"username": "admin", "password": "test-user-key"})
    token = resp.json()["access_token"]

    # Use token — will get 404 because no model connected, but not 401
    resp2 = await client.post(
        "/ask",
        json={"prompt": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code != 401


@pytest.mark.asyncio
async def test_ask_with_invalid_token(client):
    resp = await client.post(
        "/ask",
        json={"prompt": "hello"},
        headers={"Authorization": "Bearer invalid-token-xxx"},
    )
    assert resp.status_code == 401
