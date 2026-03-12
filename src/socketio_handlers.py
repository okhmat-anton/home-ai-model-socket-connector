"""Socket.IO namespace /model — handles model connections and inference."""

from __future__ import annotations

import asyncio
import time

import socketio
import structlog

from src.config import settings
from src.model_registry import registry

logger = structlog.get_logger()

# Pending inference requests: request_id → asyncio.Future
pending_requests: dict[str, asyncio.Future] = {}

# Pending stream queues: request_id → asyncio.Queue
pending_streams: dict[str, asyncio.Queue] = {}


class ModelNamespace(socketio.AsyncNamespace):
    """Socket.IO namespace for model communication."""

    def __init__(self) -> None:
        super().__init__(namespace="/model")

    async def on_connect(self, sid: str, environ: dict, auth: dict | None = None) -> bool:
        """Authenticate and register model on connect."""
        if not auth:
            logger.warning("model_connect_rejected", sid=sid, reason="no auth data")
            return False

        api_key = auth.get("api_key", "")
        model_name = auth.get("model_name", "")

        if not api_key or api_key != settings.model_api_key:
            logger.warning("model_connect_rejected", sid=sid, reason="invalid api key")
            return False

        if not model_name:
            logger.warning("model_connect_rejected", sid=sid, reason="no model_name")
            return False

        await registry.register(model_name, sid, time.time())
        logger.info("model_connected", model=model_name, sid=sid)
        return True

    async def on_disconnect(self, sid: str) -> None:
        name = await registry.unregister_by_sid(sid)
        if name:
            logger.info("model_disconnected", model=name, sid=sid)

    # ── Incoming mode: model → server (responses) ────────────────────────────

    async def on_inference_response(self, sid: str, data: dict) -> None:
        """Model sends full inference result."""
        request_id = data.get("request_id")
        if not request_id:
            return
        fut = pending_requests.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(data)

    async def on_inference_chunk(self, sid: str, data: dict) -> None:
        """Model sends a streaming chunk."""
        request_id = data.get("request_id")
        if not request_id:
            return
        queue = pending_streams.get(request_id)
        if queue:
            await queue.put(data)

    async def on_inference_error(self, sid: str, data: dict) -> None:
        """Model reports an error."""
        request_id = data.get("request_id")
        if not request_id:
            return
        # Resolve futures
        fut = pending_requests.pop(request_id, None)
        if fut and not fut.done():
            fut.set_exception(InferenceError(data.get("error", "Unknown error"), data.get("code", "ERROR")))
        # Also signal stream queues
        queue = pending_streams.get(request_id)
        if queue:
            await queue.put({"error": data.get("error", "Unknown error"), "code": data.get("code", "ERROR")})

    async def on_pong(self, sid: str, data: dict) -> None:
        pass  # keepalive ack


class InferenceError(Exception):
    def __init__(self, message: str, code: str = "ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


model_namespace = ModelNamespace()
