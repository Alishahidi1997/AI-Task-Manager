import asyncio

import httpx
import pytest

from app.llm.circuit_breaker import CircuitBreaker, CircuitOpenError, planner_circuit_breaker
from app.llm.openai_transport import post_chat_completion_async, post_chat_completion_sync


@pytest.fixture(autouse=True)
def reset_breaker():
    planner_circuit_breaker.reset()
    yield
    planner_circuit_breaker.reset()


def test_circuit_breaker_opens_after_transient_failures():
    breaker = CircuitBreaker(failure_threshold=2, reset_seconds=60)
    breaker.record_failure(transient=True)
    breaker.record_failure(transient=True)
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_planner_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {
                "choices": [{"message": {"content": '{"tool":"create_task","arguments":{}}'}}]
            }

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("err", request=request, response=response)

        def json(self):
            return self._payload

    async def fake_post(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResponse(429)
        return FakeResponse(200)

    async def run():
        async with httpx.AsyncClient() as client:
            monkeypatch.setattr(client, "post", fake_post)
            return await post_chat_completion_async(client, {"model": "gpt-4o-mini", "messages": []})

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_PLANNER_MAX_RETRIES", "3")
    monkeypatch.setenv("OPENAI_PLANNER_RETRY_BASE_SECONDS", "0")
    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr("app.llm.openai_transport.asyncio.sleep", _noop_sleep)

    data = asyncio.run(run())
    assert "choices" in data
    assert calls["n"] == 3


def test_planner_sync_raises_when_circuit_open(monkeypatch):
    planner_circuit_breaker.reset()
    planner_circuit_breaker.record_failure(transient=True)
    planner_circuit_breaker.record_failure(transient=True)
    planner_circuit_breaker.record_failure(transient=True)
    planner_circuit_breaker.record_failure(transient=True)
    planner_circuit_breaker.record_failure(transient=True)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(CircuitOpenError):
        post_chat_completion_sync({"model": "gpt-4o-mini", "messages": []})
