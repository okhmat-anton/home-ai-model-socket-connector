"""Shared fixtures for tests."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test env vars before importing app
os.environ.update({
    "HOST": "0.0.0.0",
    "PORT": "10666",
    "MODEL_API_KEY": "test-model-key",
    "USER_API_KEY": "test-user-key",
    "SECRET_KEY": "test-secret-key-0123456789abcdef",
    "REQUEST_TIMEOUT": "5",
    "MAX_CONCURRENT_REQUESTS": "3",
    "PROXY_PORT": "10667",
    "PROXY_USER": "testproxy",
    "PROXY_PASSWORD": "testproxypass",
    "PROXY_ALLOWED_DOMAINS": "*",
    "PROXY_MAX_CONNECTIONS": "5",
    "LOG_LEVEL": "DEBUG",
})

from src.config import Settings
from src.main import app, sio
from src.model_registry import registry


@pytest_asyncio.fixture(autouse=True)
async def _clean_registry():
    """Clear registry before each test."""
    registry._models.clear()
    yield
    registry._models.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def auth_headers():
    """Valid user auth headers."""
    return {"Authorization": "Bearer test-user-key"}


@pytest_asyncio.fixture
async def connected_model():
    """Register a mock model in the registry."""
    await registry.register("test-model", "fake-sid-123", 1000.0)
    return "test-model"
