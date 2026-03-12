"""Tests for GET /instruction."""

import pytest


@pytest.mark.asyncio
async def test_instruction_returns_200(client):
    resp = await client.get("/instruction")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_instruction_is_plain_text(client):
    resp = await client.get("/instruction")
    assert "text/plain" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_instruction_contains_code_examples(client):
    resp = await client.get("/instruction")
    text = resp.text
    assert "httpx" in text
    assert "/ask" in text
    assert "proxy" in text.lower()


@pytest.mark.asyncio
async def test_instruction_contains_port(client):
    resp = await client.get("/instruction")
    assert "10666" in resp.text


@pytest.mark.asyncio
async def test_instruction_no_auth_required(client):
    resp = await client.get("/instruction")
    assert resp.status_code == 200
