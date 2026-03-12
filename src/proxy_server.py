"""HTTPS proxy server (outbound mode) — asyncio-based HTTP CONNECT proxy with Basic Auth."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
import time

import structlog

from src.config import settings

logger = structlog.get_logger()

# Track active connections
_active_connections = 0
_conn_lock = asyncio.Lock()

# Private networks (SSRF protection)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(host: str) -> bool:
    """Check if host resolves to a private IP."""
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        # It's a hostname — resolve it
        try:
            info = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in info:
                addr = ipaddress.ip_address(sockaddr[0])
                if any(addr in net for net in _PRIVATE_NETWORKS):
                    return True
        except socket.gaierror:
            pass
    return False


def _check_auth(header_line: str) -> bool:
    """Verify Proxy-Authorization Basic header."""
    if not header_line:
        return False
    try:
        parts = header_line.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "basic":
            return False
        decoded = base64.b64decode(parts[1]).decode("utf-8")
        user, password = decoded.split(":", 1)
        return user == settings.proxy_user and password == settings.proxy_password
    except Exception:
        return False


def _is_domain_allowed(host: str) -> bool:
    """Check if domain is in allowed list."""
    allowed = settings.proxy_domain_list
    if allowed is None:
        return True  # * = allow all
    return any(host == d or host.endswith("." + d) for d in allowed)


def _parse_host_port(target: str, default_port: int = 443) -> tuple[str, int]:
    """Parse host:port string."""
    if ":" in target:
        host, port_str = target.rsplit(":", 1)
        try:
            return host, int(port_str)
        except ValueError:
            pass
    return target, default_port


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> int:
    """Copy data from reader to writer. Returns bytes transferred."""
    total = 0
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
            total += len(data)
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    return total


async def _handle_connect(
    method: str,
    target: str,
    headers: dict[str, str],
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    """Handle HTTP CONNECT tunnel."""
    host, port = _parse_host_port(target, 443)

    # Check domain
    if not _is_domain_allowed(host):
        client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        await client_writer.drain()
        logger.warning("proxy_blocked_domain", host=host)
        return

    # Check SSRF
    if _is_private_ip(host):
        client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        await client_writer.drain()
        logger.warning("proxy_blocked_ssrf", host=host)
        return

    try:
        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=30
        )
    except Exception as e:
        client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        await client_writer.drain()
        logger.error("proxy_connect_failed", host=host, port=port, error=str(e))
        return

    client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await client_writer.drain()

    start = time.monotonic()
    task1 = asyncio.create_task(_pipe(client_reader, remote_writer))
    task2 = asyncio.create_task(_pipe(remote_reader, client_writer))
    await asyncio.gather(task1, task2, return_exceptions=True)
    elapsed = time.monotonic() - start

    bytes_up = task1.result() if task1.done() and not task1.cancelled() else 0
    bytes_down = task2.result() if task2.done() and not task2.cancelled() else 0

    remote_writer.close()

    logger.info("proxy_tunnel_closed", host=host, port=port, bytes_up=bytes_up, bytes_down=bytes_down, elapsed=round(elapsed, 2))


async def _handle_http(
    method: str,
    url: str,
    headers: dict[str, str],
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    raw_request: bytes,
) -> None:
    """Handle plain HTTP proxy request (non-CONNECT)."""
    # Parse URL
    if url.startswith("http://"):
        url_no_scheme = url[7:]
    else:
        url_no_scheme = url

    slash_idx = url_no_scheme.find("/")
    if slash_idx == -1:
        host_port = url_no_scheme
        path = "/"
    else:
        host_port = url_no_scheme[:slash_idx]
        path = url_no_scheme[slash_idx:]

    host, port = _parse_host_port(host_port, 80)

    if not _is_domain_allowed(host):
        client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        await client_writer.drain()
        return

    if _is_private_ip(host):
        client_writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        await client_writer.drain()
        return

    try:
        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=30
        )
    except Exception:
        client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        await client_writer.drain()
        return

    # Rebuild request with relative path
    new_headers = {k: v for k, v in headers.items() if k.lower() != "proxy-authorization"}
    request_line = f"{method} {path} HTTP/1.1\r\n"
    header_lines = "".join(f"{k}: {v}\r\n" for k, v in new_headers.items())
    rebuilt = (request_line + header_lines + "\r\n").encode()

    remote_writer.write(rebuilt)
    await remote_writer.drain()

    # Pipe response back
    await _pipe(remote_reader, client_writer)

    remote_writer.close()


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle a single proxy connection."""
    global _active_connections

    peername = writer.get_extra_info("peername", ("?", 0))

    async with _conn_lock:
        if _active_connections >= settings.proxy_max_connections:
            writer.write(b"HTTP/1.1 503 Service Unavailable\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        _active_connections += 1

    try:
        # Read the first line
        raw_lines = b""
        first_line = await asyncio.wait_for(reader.readline(), timeout=30)
        if not first_line:
            return
        raw_lines += first_line

        parts = first_line.decode("utf-8", errors="replace").strip().split(" ")
        if len(parts) < 2:
            return

        method = parts[0].upper()
        target = parts[1]

        # Read headers
        headers: dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=30)
            raw_lines += line
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                break
            if ":" in decoded:
                key, val = decoded.split(":", 1)
                headers[key.strip()] = val.strip()

        # Auth check
        auth_header = headers.get("Proxy-Authorization", "")
        if not _check_auth(auth_header):
            writer.write(
                b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                b"Proxy-Authenticate: Basic realm=\"proxy\"\r\n\r\n"
            )
            await writer.drain()
            logger.warning("proxy_auth_failed", client=peername[0])
            return

        if method == "CONNECT":
            await _handle_connect(method, target, headers, reader, writer)
        else:
            await _handle_http(method, target, headers, reader, writer, raw_lines)

    except asyncio.TimeoutError:
        logger.warning("proxy_timeout", client=peername[0])
    except Exception as e:
        logger.error("proxy_error", client=peername[0], error=str(e))
    finally:
        async with _conn_lock:
            _active_connections -= 1
        writer.close()


async def start_proxy_server() -> asyncio.AbstractServer:
    """Start the HTTPS proxy server."""
    server = await asyncio.start_server(
        _handle_client,
        host=settings.host,
        port=settings.proxy_port,
    )
    logger.info("proxy_started", host=settings.host, port=settings.proxy_port)
    return server
