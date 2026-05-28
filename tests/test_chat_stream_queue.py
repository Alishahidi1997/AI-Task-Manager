"""Queued /chat/stream with Redis-backed SSE."""

import json
from unittest.mock import AsyncMock, patch

from fastapi import Request

from app.queue.config import JOB_CHAT_STREAM
from app.services.chat_stream_buffer import append_stream_event, iter_stream_events, stream_key
from tests.conftest import auth_headers


class FakeRedis:
    def __init__(self):
        self.lists: dict[str, list[str]] = {}
        self.kv: dict[str, str] = {}

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if end == -1:
            end = len(items) - 1
        return items[start : end + 1] if items else []

    async def expire(self, key, _ttl):
        return True

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):  # noqa: ARG002
        self.kv[key] = value

    async def incr(self, key):
        current = int(self.kv.get(key, 0))
        current += 1
        self.kv[key] = str(current)
        return current


def test_append_and_iter_stream_events():
    import asyncio

    async def run():
        redis = FakeRedis()
        job_id = "job-test-stream"
        await append_stream_event(redis, job_id, {"event": "start"})
        await append_stream_event(redis, job_id, {"event": "planner_token", "text": "{"})
        await append_stream_event(redis, job_id, {"event": "result", "status": "executed"})
        await append_stream_event(redis, job_id, {"event": "stream_end"})

        events = []
        async for evt in iter_stream_events(redis, job_id, timeout_seconds=1.0):
            events.append(evt)
        assert events[0]["event"] == "start"
        assert events[-1]["event"] == "result"

    asyncio.run(run())


@patch("app.routes.chat.enqueue_chat_stream", new_callable=AsyncMock)
@patch("app.routes.chat.chat_stream_queue_enabled", return_value=True)
def test_chat_stream_returns_202_when_queue_enabled(_mock_enabled, mock_enqueue, client):
    from app.deps import get_redis
    from app.main import app

    job_id = "00000000-0000-0000-0000-000000000099"
    mock_enqueue.return_value = job_id
    def _fake_redis(request: Request):  # noqa: ARG001
        return FakeRedis()

    app.dependency_overrides[get_redis] = _fake_redis

    headers = auth_headers(client, "stream-queue@example.com", "secret123")
    try:
        response = client.post(
            "/chat/stream",
            headers=headers,
            json={"message": "Create a task due tomorrow", "source": "pytest"},
        )
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["job_id"] == job_id
        assert body["stream_url"].endswith("/stream")
        mock_enqueue.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_redis, None)


def test_stream_job_endpoint_reads_redis(client, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    from app.database import SessionLocal
    from app.models import LLMJob, User
    from app.services.llm_jobs import create_llm_job

    headers = auth_headers(client, "stream-read@example.com", "secret123")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "stream-read@example.com").first()
        row = create_llm_job(
            db,
            job_type=JOB_CHAT_STREAM,
            user_id=user.id,
            tenant_id=f"user-{user.id}",
            request_text="hello",
            channel="api",
            payload={"message": "hello"},
        )
        job_id = row.job_id
    finally:
        db.close()

    fake = FakeRedis()

    def fake_get_redis(request: Request):  # noqa: ARG001
        return fake

    async def seed():
        await append_stream_event(fake, job_id, {"event": "start"})
        await append_stream_event(fake, job_id, {"event": "result", "status": "executed"})
        await append_stream_event(fake, job_id, {"event": "stream_end"})

    import asyncio

    asyncio.run(seed())

    from app.main import app
    from app.deps import get_redis

    app.dependency_overrides[get_redis] = fake_get_redis
    try:
        with client.stream("GET", f"/jobs/{job_id}/stream", headers=headers) as response:
            assert response.status_code == 200
            chunks = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    chunks.append(json.loads(line[6:]))
            assert chunks[0]["event"] == "start"
            assert any(c.get("event") == "result" for c in chunks)
    finally:
        app.dependency_overrides.pop(get_redis, None)
