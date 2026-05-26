"""Redis-backed event buffer for queued /chat/stream (Epic 1.2)."""

from __future__ import annotations

import asyncio
import json
import os
import time

STREAM_TTL_SECONDS = int(os.getenv("CHAT_STREAM_REDIS_TTL_SECONDS", "3600"))
STREAM_POLL_INTERVAL = float(os.getenv("CHAT_STREAM_POLL_INTERVAL_SECONDS", "0.05"))


def stream_key(job_id: str) -> str:
    return f"chat:stream:{job_id}"


async def append_stream_event(redis, job_id: str, event: dict) -> None:
    if redis is None:
        raise RuntimeError("redis is required for chat stream buffer")
    await redis.rpush(stream_key(job_id), json.dumps(event, ensure_ascii=True, default=str))
    await redis.expire(stream_key(job_id), STREAM_TTL_SECONDS)


async def iter_stream_events(redis, job_id: str, *, timeout_seconds: float = 120.0):
    """Yield events as the worker appends them until stream_end, result, or error."""
    if redis is None:
        raise RuntimeError("redis is required for chat stream buffer")

    index = 0
    deadline = time.monotonic() + timeout_seconds
    key = stream_key(job_id)

    while time.monotonic() < deadline:
        items = await redis.lrange(key, index, -1)
        if items:
            for raw in items:
                event = json.loads(raw)
                yield event
                index += 1
                if event.get("event") in {"stream_end", "result", "error"}:
                    return
        else:
            status = await redis.get(f"{key}:status")
            if status == "failed":
                yield {"event": "error", "detail": "stream job failed"}
                return
        await asyncio.sleep(STREAM_POLL_INTERVAL)

    yield {"event": "error", "detail": "stream timed out waiting for events"}


async def set_stream_status(redis, job_id: str, status: str) -> None:
    await redis.set(f"{stream_key(job_id)}:status", status, ex=STREAM_TTL_SECONDS)
