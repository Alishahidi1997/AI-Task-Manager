"""Circuit breaker for OpenAI planner calls (Stretch ops)."""

from __future__ import annotations

import os
import time
from threading import Lock


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and calls are short-circuited."""


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int | None = None,
        reset_seconds: float | None = None,
    ):
        self.failure_threshold = int(
            failure_threshold or os.getenv("OPENAI_CIRCUIT_FAILURE_THRESHOLD", "5")
        )
        self.reset_seconds = float(reset_seconds or os.getenv("OPENAI_CIRCUIT_RESET_SECONDS", "30"))
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if (time.monotonic() - self._opened_at) >= self.reset_seconds:
                return "half_open"
            return "open"

    def before_call(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.reset_seconds:
                return
            raise CircuitOpenError(
                f"OpenAI circuit breaker is open ({self.reset_seconds - elapsed:.0f}s remaining)"
            )

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self, *, transient: bool) -> None:
        if not transient:
            return
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None


# Shared breaker for planner traffic in this process.
planner_circuit_breaker = CircuitBreaker()
