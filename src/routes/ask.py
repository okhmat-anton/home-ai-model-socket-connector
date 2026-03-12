"""POST /ask — send inference request to model."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.auth import require_user_auth
from src.config import settings
from src.model_registry import registry
from src.schemas import AskRequest, AskResponse, UsageInfo
from src.socketio_handlers import InferenceError, pending_requests, pending_streams

router = APIRouter()

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    return _semaphore


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, _user: str = Depends(require_user_auth)):
    model_name = body.model or settings.base_model

    if not await registry.is_connected(model_name):
        available = await registry.list_names()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_name}' not connected. Available: {available}",
        )

    sem = _get_semaphore()
    if sem.locked() and sem._value == 0:  # type: ignore[attr-defined]
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many concurrent requests")

    async with sem:
        sid = await registry.get_sid(model_name)
        if not sid:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model disconnected")

        request_id = str(uuid.uuid4())
        params = body.parameters.model_dump() if body.parameters else {}

        # Import sio from main to emit events
        from src.main import sio

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
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail="Model response timed out")
    except InferenceError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)

    elapsed = time.monotonic() - start
    usage_data = data.get("usage", {})
    return AskResponse(
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
                    yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
                    break

                if "error" in chunk:
                    yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                    break

                done = chunk.get("done", False)
                payload: dict = {"token": chunk.get("token", ""), "done": done}
                if done:
                    payload["usage"] = chunk.get("usage", {})
                    payload["elapsed_seconds"] = round(time.monotonic() - start, 2)
                yield f"data: {json.dumps(payload)}\n\n"

                if done:
                    break
        finally:
            pending_streams.pop(request_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
