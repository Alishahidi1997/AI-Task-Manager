"""Shared OpenAI HTTP transport: retries, circuit breaker, metrics."""

from __future__ import annotations

import asyncio
import os
import time

import httpx

from app.llm.circuit_breaker import CircuitOpenError, planner_circuit_breaker
from app.metrics.prometheus import record_circuit_trip, record_planner_outcome, record_planner_retry

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _max_retries() -> int:
    return int(os.getenv("OPENAI_PLANNER_MAX_RETRIES", "3"))


def _retry_delay(attempt: int) -> float:
    base = float(os.getenv("OPENAI_PLANNER_RETRY_BASE_SECONDS", "0.5"))
    return base * (2**attempt)


def _api_headers() -> dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _trip_breaker_if_needed() -> None:
    if planner_circuit_breaker.state == "open":
        record_circuit_trip()


async def post_chat_completion_async(client: httpx.AsyncClient, payload: dict) -> dict:
    planner_circuit_breaker.before_call()
    last_exc: Exception | None = None
    retries = _max_retries()

    for attempt in range(retries + 1):
        try:
            response = await client.post(OPENAI_CHAT_URL, headers=_api_headers(), json=payload)
            response.raise_for_status()
            planner_circuit_breaker.record_success()
            record_planner_outcome("success")
            return response.json()
        except CircuitOpenError:
            record_planner_outcome("circuit_open")
            raise
        except Exception as exc:
            last_exc = exc
            transient = _is_transient(exc)
            if transient:
                planner_circuit_breaker.record_failure(transient=True)
                if planner_circuit_breaker.state == "open":
                    _trip_breaker_if_needed()
            if not transient or attempt >= retries:
                record_planner_outcome("error")
                raise
            record_planner_retry()
            await asyncio.sleep(_retry_delay(attempt))

    record_planner_outcome("error")
    raise last_exc  # pragma: no cover


def post_chat_completion_sync(payload: dict) -> dict:
    planner_circuit_breaker.before_call()
    last_exc: Exception | None = None
    retries = _max_retries()

    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=45.0) as client:
                response = client.post(OPENAI_CHAT_URL, headers=_api_headers(), json=payload)
                response.raise_for_status()
            planner_circuit_breaker.record_success()
            record_planner_outcome("success")
            return response.json()
        except CircuitOpenError:
            record_planner_outcome("circuit_open")
            raise
        except Exception as exc:
            last_exc = exc
            transient = _is_transient(exc)
            if transient:
                planner_circuit_breaker.record_failure(transient=True)
                if planner_circuit_breaker.state == "open":
                    _trip_breaker_if_needed()
            if not transient or attempt >= retries:
                record_planner_outcome("error")
                raise
            record_planner_retry()
            time.sleep(_retry_delay(attempt))

    record_planner_outcome("error")
    raise last_exc  # pragma: no cover
