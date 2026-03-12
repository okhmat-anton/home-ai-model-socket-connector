"""Main entry point — FastAPI app + Socket.IO + Proxy server."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import socketio
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.proxy_server import start_proxy_server
from src.socketio_handlers import model_namespace

# ── Logging setup ────────────────────────────────────────────────────────────

_log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
)

logger = structlog.get_logger()

# ── Socket.IO ────────────────────────────────────────────────────────────────

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
sio.register_namespace(model_namespace)

# ── FastAPI app ──────────────────────────────────────────────────────────────

_proxy_server: asyncio.AbstractServer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _proxy_server
    logger.info("server_starting", port=settings.port, proxy_port=settings.proxy_port)
    _proxy_server = await start_proxy_server()
    # Start keepalive task
    keepalive_task = asyncio.create_task(_keepalive_loop())
    yield
    keepalive_task.cancel()
    if _proxy_server:
        _proxy_server.close()
        await _proxy_server.wait_closed()
    logger.info("server_stopped")


app = FastAPI(title="Home AI Model Socket Connector", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────────────────

from src.routes.ask import router as ask_router
from src.routes.auth import router as auth_router
from src.routes.health import router as health_router
from src.routes.instruction import router as instruction_router
from src.routes.models import router as models_router

app.include_router(instruction_router)
app.include_router(health_router)
app.include_router(ask_router)
app.include_router(models_router)
app.include_router(auth_router)

# ── Mount Socket.IO as ASGI sub-app ─────────────────────────────────────────

sio_app = socketio.ASGIApp(sio, other_asgi_app=app)


# ── Keepalive ────────────────────────────────────────────────────────────────

async def _keepalive_loop() -> None:
    """Send ping to all connected models every 30 seconds."""
    import time

    while True:
        await asyncio.sleep(30)
        try:
            from src.model_registry import registry

            names = await registry.list_names()
            for name in names:
                sid = await registry.get_sid(name)
                if sid:
                    await sio.emit("ping", {"timestamp": time.time()}, to=sid, namespace="/model")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("keepalive_error", error=str(e))


# ── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    uvicorn.run(
        "src.main:sio_app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
