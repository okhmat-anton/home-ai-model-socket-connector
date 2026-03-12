"""POST /ask — send inference request to model."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.auth import require_user_auth
from src.config import settings
from src.error_store import error_store
from src.model_registry import registry
from src.schemas import AskRequest, AskResponse, UsageInfo
from src.socketio_handlers import InferenceError, pending_requests, pending_streams

logger = structlog.get_logger()
router = APIRouter()

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    return _semaphore


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, _user: str = Depends(require_user_auth)):
    # If no model specified, use the first connected model
    if body.model:
        model_name = body.model
    else:
        available = await registry.list_names()
        if not available:
            request_id = body.request_id or str(uuid.uuid4())
            detail = "No models connected"
            error_store.add(request_id, "model_not_found", detail)
            logger.warning("model_not_found", request_id=request_id, detail=detail)
            raise HTTPException(status_code=404, detail=detail, headers={"X-Request-ID": request_id})
        model_name = available[0]

    request_id = body.request_id or str(uuid.uuid4())

    if not await registry.is_connected(model_name):
        available = await registry.list_names()
        detail = f"Model '{model_name}' not connected. Available: {available}"
        error_store.add(request_id, "model_not_found", detail, model=model_name)
        logger.warning("model_not_found", request_id=request_id, model=model_name, available=available)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            headers={"X-Request-ID": request_id},
        )

    sem = _get_semaphore()
    if sem.locked() and sem._value == 0:  # type: ignore[attr-defined]
        error_store.add(request_id, "rate_limited", "Too many concurrent requests", model=model_name)
        logger.warning("rate_limited", request_id=request_id, model=model_name)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent requests",
            headers={"X-Request-ID": request_id},
        )

    async with sem:
        sid = await registry.get_sid(model_name)
        if not sid:
            error_store.add(request_id, "model_disconnected", "Model disconnected during request", model=model_name)
            logger.error("model_disconnected", request_id=request_id, model=model_name)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Model disconnected",
                headers={"X-Request-ID": request_id},
            )

        params = body.parameters.model_dump() if body.parameters else {}

        # Import sio from main to emit events
        from src.main import sio

        logger.info("ask_request", request_id=request_id, model=model_name, stream=body.stream,
                    prompt_len=len(body.prompt))

        if body.stream:
            return await _handle_stream(sio, sid, request_id, body.prompt, params, model_name)
        else:
            return await _handle_sync(sio, sid, request_id, body.prompt, params, model_name)


async def _handle_sync(sio, sid, request_id, prompt, params, model_name) -> AskResponse:
    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    pending_requests[request_id] = fut

    start = time.monotonic()
    await sio.emit(
        "inference_request",
        {"request_id": request_id, "prompt": prompt, "parameters": params},
        to=sid,
        namespace="/model",
    )

    try:
        data = await asyncio.wait_for(fut, timeout=settings.request_timeout)
    except asyncio.TimeoutError:
        pending_requests.pop(request_id, None)
        error_store.add(request_id, "ask_timeout", "Model response timed out",
                        model=model_name, timeout=settings.request_timeout)
        logger.error("ask_timeout", request_id=request_id, model=model_name,
                     timeout=settings.request_timeout)
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Model response timed out",
            headers={"X-Request-ID": request_id},
        )
    except InferenceError as e:
        error_store.add(request_id, "inference_error", e.message,
                        model=model_name, code=e.code)
        logger.error("inference_error", request_id=request_id, model=model_name,
                     error=e.message, code=e.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=e.message,
            headers={"X-Request-ID": request_id},
        )

    elapsed = time.monotonic() - start
    logger.info("ask_response", request_id=request_id, model=model_name, elapsed=round(elapsed, 2))
    usage_data = data.get("usage", {})
    return AskResponse(
        request_id=request_id,
        response=data.get("response", ""),
        model=model_name,
        usage=UsageInfo(**usage_data) if usage_data else UsageInfo(),
        elapsed_seconds=round(elapsed, 2),
    )


async def _handle_stream(sio, sid, request_id, prompt, params, model_name):
    queue: asyncio.Queue = asyncio.Queue()
    pending_streams[request_id] = queue

    await sio.emit(
        "inference_request",
        {"request_id": request_id, "prompt": prompt, "parameters": params, "stream": True},
        to=sid,
        namespace="/model",
    )

    async def event_generator():
        start = time.monotonic()
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=settings.request_timeout)
                except asyncio.TimeoutError:
                    error_store.add(request_id, "stream_timeout", "Stream timed out", model=model_name)
                    logger.error("stream_timeout", request_id=request_id, model=model_name)
                    yield f"data: {json.dumps({'request_id': request_id, 'error': 'timeout'})}\n\n"
                    break

                if "error" in chunk:
                    error_store.add(request_id, "stream_error", chunk["error"], model=model_name)
                    logger.error("stream_error", request_id=request_id, error=chunk["error"])
                    yield f"data: {json.dumps({'request_id': request_id, 'error': chunk['error']})}\n\n"
                    break

                done = chunk.get("done", False)
                payload: dict = {"request_id": request_id, "token": chunk.get("token", ""), "done": done}
                if done:
                    payload["usage"] = chunk.get("usage", {})
                    payload["elapsed_seconds"] = round(time.monotonic() - start, 2)
                yield f"data: {json.dumps(payload)}\n\n"

                if done:
                    break
        finally:
            pending_streams.pop(request_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
