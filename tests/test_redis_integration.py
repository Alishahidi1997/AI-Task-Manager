"""Redis integration (Phase 3.4). Skipped unless RUN_REDIS_INTEGRATION=1 and REDIS_URL are set."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi import HTTPException

from app.services.rate_limit import enforce_chat_rate_limit, enforce_slack_rate_limit

pytestmark = pytest.mark.skipif(
    not (
        os.getenv("REDIS_URL", "").strip()
        and os.getenv("RUN_REDIS_INTEGRATION", "").strip().lower() in {"1", "true", "yes", "on"}
    ),
    reason="set RUN_REDIS_INTEGRATION=1 and REDIS_URL for Redis integration tests",
)


async def _redis_client():
    import redis.asyncio as redis_async

    client = redis_async.from_url(os.environ["REDIS_URL"].strip(), decode_responses=True)
    await client.ping()
    await client.flushdb()
    return client


def test_redis_chat_rate_limit_against_broker(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_CHAT_PER_MINUTE", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")

    async def run():
        redis = await _redis_client()
        try:
            await enforce_chat_rate_limit(redis, user_id=9001)
            await enforce_chat_rate_limit(redis, user_id=9001)
            with pytest.raises(HTTPException) as exc:
                await enforce_chat_rate_limit(redis, user_id=9001)
            assert exc.value.status_code == 429
            assert exc.value.headers.get("Retry-After")
        finally:
            await redis.aclose()

    asyncio.run(run())


def test_redis_slack_rate_limit_against_broker(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_SLACK_PER_MINUTE", "1")

    async def run():
        redis = await _redis_client()
        try:
            await enforce_slack_rate_limit(redis, slack_user_id="U_CI_REDIS")
            with pytest.raises(HTTPException) as exc:
                await enforce_slack_rate_limit(redis, slack_user_id="U_CI_REDIS")
            assert exc.value.status_code == 429
        finally:
            await redis.aclose()

    asyncio.run(run())


def test_redis_snapshot_cache_setex_get():
    """Mirror insights /snapshot cache keys (setex + get)."""

    async def run():
        redis = await _redis_client()
        try:
            payload = {"generated_at": "ci-test", "productivity": {"bucket_count": 0}}
            key = "cache:insights:snapshot:42:30:7"
            await redis.setex(key, 30, json.dumps(payload, ensure_ascii=True))
            raw = await redis.get(key)
            assert raw is not None
            assert json.loads(raw)["generated_at"] == "ci-test"
            ttl = await redis.ttl(key)
            assert ttl > 0
        finally:
            await redis.aclose()

    asyncio.run(run())
