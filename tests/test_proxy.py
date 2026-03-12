"""Tests for HTTPS proxy server."""

from __future__ import annotations

import asyncio
import base64

import pytest

from src.proxy_server import _check_auth, _is_domain_allowed, _is_private_ip, _parse_host_port


# ── Unit tests for helpers ───────────────────────────────────────────────────

def test_check_auth_valid():
    creds = base64.b64encode(b"testproxy:testproxypass").decode()
    assert _check_auth(f"Basic {creds}") is True


def test_check_auth_invalid_password():
    creds = base64.b64encode(b"testproxy:wrong").decode()
    assert _check_auth(f"Basic {creds}") is False


def test_check_auth_empty():
    assert _check_auth("") is False


def test_check_auth_no_basic():
    assert _check_auth("Bearer token123") is False


def test_is_domain_allowed_wildcard():
    assert _is_domain_allowed("anything.com") is True


def test_parse_host_port():
    assert _parse_host_port("example.com:443") == ("example.com", 443)
    assert _parse_host_port("example.com") == ("example.com", 443)
    assert _parse_host_port("example.com:8080") == ("example.com", 8080)


def test_is_private_ip_localhost():
    assert _is_private_ip("127.0.0.1") is True


def test_is_private_ip_10():
    assert _is_private_ip("10.0.0.1") is True


def test_is_private_ip_192():
    assert _is_private_ip("192.168.1.1") is True


def test_is_private_ip_public():
    assert _is_private_ip("8.8.8.8") is False


# ── Integration tests for proxy server ───────────────────────────────────────

@pytest.mark.asyncio
async def test_proxy_407_no_auth():
    """CONNECT without auth should return 407."""
    server = await asyncio.start_server(
        lambda r, w: None,
        "127.0.0.1",
        0,
    )
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    # Start real proxy on a free port
    from src.proxy_server import _handle_client

    proxy_server = await asyncio.start_server(_handle_client, "127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()

        response = await asyncio.wait_for(reader.read(4096), timeout=5)
        assert b"407" in response
        writer.close()
    finally:
        proxy_server.close()
        await proxy_server.wait_closed()


@pytest.mark.asyncio
async def test_proxy_407_wrong_credentials():
    """CONNECT with wrong auth should return 407."""
    from src.proxy_server import _handle_client

    proxy_server = await asyncio.start_server(_handle_client, "127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        bad_creds = base64.b64encode(b"wrong:wrong").decode()
        writer.write(
            f"CONNECT example.com:443 HTTP/1.1\r\n"
            f"Proxy-Authorization: Basic {bad_creds}\r\n\r\n".encode()
        )
        await writer.drain()

        response = await asyncio.wait_for(reader.read(4096), timeout=5)
        assert b"407" in response
        writer.close()
    finally:
        proxy_server.close()
        await proxy_server.wait_closed()


@pytest.mark.asyncio
async def test_proxy_403_localhost():
    """CONNECT to localhost should return 403 (SSRF protection)."""
    from src.proxy_server import _handle_client

    proxy_server = await asyncio.start_server(_handle_client, "127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
        creds = base64.b64encode(b"testproxy:testproxypass").decode()
        writer.write(
            f"CONNECT 127.0.0.1:8080 HTTP/1.1\r\n"
            f"Proxy-Authorization: Basic {creds}\r\n\r\n".encode()
        )
        await writer.drain()

        response = await asyncio.wait_for(reader.read(4096), timeout=5)
        assert b"403" in response
        writer.close()
    finally:
        proxy_server.close()
        await proxy_server.wait_closed()
