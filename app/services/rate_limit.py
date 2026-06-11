"""Redis-backed fixed-window rate limits (Epic 1 — replaces counter-only usage)."""

from __future__ import annotations

import os

from fastapi import HTTPException, status

def _window_seconds() -> int:
    return int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


def _chat_limit() -> int:
    return int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "30"))


def _slack_limit() -> int:
    return int(os.getenv("RATE_LIMIT_SLACK_PER_MINUTE", "60"))


def _tenant_ai_hourly_limit() -> int:
    return int(os.getenv("WORKSPACE_AI_REQUESTS_PER_HOUR", "0"))


def rate_limit_enabled() -> bool:
    flag = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def snapshot_cache_ttl() -> int:
    return max(0, int(os.getenv("INSIGHTS_SNAPSHOT_CACHE_SECONDS", "60")))


async def _consume_slot(redis, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """
    Fixed window: INCR key, EXPIRE on first hit.
    Returns (allowed, retry_after_seconds).
    """
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count <= limit:
        return True, 0
    ttl = await redis.ttl(key)
    retry_after = int(ttl) if ttl and ttl > 0 else window_seconds
    return False, retry_after


def _too_many_requests(retry_after: int, *, scope: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"rate limit exceeded for {scope}; retry after {retry_after} second(s)",
        headers={"Retry-After": str(retry_after)},
    )


async def enforce_chat_rate_limit(redis, user_id: int) -> None:
    if redis is None or not rate_limit_enabled():
        return
    key = f"ratelimit:chat:user:{user_id}"
    allowed, retry_after = await _consume_slot(redis, key, _chat_limit(), _window_seconds())
    if not allowed:
        raise _too_many_requests(retry_after, scope="chat")


async def enforce_slack_rate_limit(
    redis,
    *,
    slack_user_id: str,
    internal_user_id: int | None = None,
    check_slack_uid: bool = True,
) -> None:
    if redis is None or not rate_limit_enabled():
        return
    if check_slack_uid:
        key = f"ratelimit:slack:uid:{slack_user_id}"
        allowed, retry_after = await _consume_slot(redis, key, _slack_limit(), _window_seconds())
        if not allowed:
            raise _too_many_requests(retry_after, scope="slack")
    if internal_user_id is not None:
        key_user = f"ratelimit:slack:user:{internal_user_id}"
        allowed_u, retry_u = await _consume_slot(redis, key_user, _slack_limit(), _window_seconds())
        if not allowed_u:
            raise _too_many_requests(retry_u, scope="slack")


async def enforce_tenant_ai_rate_limit(redis, tenant_id: str) -> None:
    """Optional per-tenant cap on AI/orchestration endpoints (hourly window)."""
    limit = _tenant_ai_hourly_limit()
    if limit <= 0 or redis is None or not rate_limit_enabled():
        return
    key = f"ratelimit:ai:tenant:{tenant_id}"
    allowed, retry_after = await _consume_slot(redis, key, limit, 3600)
    if not allowed:
        raise _too_many_requests(retry_after, scope=f"tenant ai ({tenant_id})")


async def bump_stat(redis, stat_key: str) -> None:
    """Optional metrics counters (preserves previous stats:* behavior)."""
    if redis is None:
        return
    await redis.incr(stat_key)
