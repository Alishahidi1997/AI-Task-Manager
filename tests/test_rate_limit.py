import asyncio

import pytest
from fastapi import HTTPException

from app.services.rate_limit import enforce_chat_rate_limit, enforce_slack_rate_limit


class FakeRedis:
    def __init__(self):
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, 60)


def test_chat_rate_limit_blocks_after_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_CHAT_PER_MINUTE", "2")
    redis = FakeRedis()

    async def run():
        await enforce_chat_rate_limit(redis, 42)
        await enforce_chat_rate_limit(redis, 42)
        with pytest.raises(HTTPException) as exc:
            await enforce_chat_rate_limit(redis, 42)
        assert exc.value.status_code == 429
        assert exc.value.headers.get("Retry-After")

    asyncio.run(run())


def test_slack_rate_limit_per_uid(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_SLACK_PER_MINUTE", "1")
    redis = FakeRedis()

    async def run():
        await enforce_slack_rate_limit(redis, slack_user_id="U123")
        with pytest.raises(HTTPException) as exc:
            await enforce_slack_rate_limit(redis, slack_user_id="U123")
        assert exc.value.status_code == 429

    asyncio.run(run())


def test_rate_limit_skipped_without_redis(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    asyncio.run(enforce_chat_rate_limit(None, 1))
