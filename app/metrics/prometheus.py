"""Prometheus metric definitions and /metrics handler."""

from __future__ import annotations

import re

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
OPENAI_PLANNER_REQUESTS = Counter(
    "openai_planner_requests_total",
    "OpenAI planner completion calls",
    ["outcome"],
)
OPENAI_PLANNER_RETRIES = Counter(
    "openai_planner_retries_total",
    "Planner retries on transient OpenAI errors",
)
OPENAI_CIRCUIT_STATE = Counter(
    "openai_circuit_breaker_trips_total",
    "Times the OpenAI planner circuit breaker opened",
)

_ID_SEGMENT = re.compile(r"^/\d+(/|$)")


def metric_path(path: str) -> str:
    """Collapse numeric IDs to keep Prometheus cardinality low."""
    if path == "/metrics":
        return path
    parts = []
    for segment in path.split("/"):
        if segment.isdigit():
            parts.append(":id")
        else:
            parts.append(segment)
    normalized = "/".join(parts)
    return normalized or "/"


def record_http_request(method: str, path: str, status: int, duration_seconds: float) -> None:
    label_path = metric_path(path)
    HTTP_REQUESTS.labels(method=method, path=label_path, status=str(status)).inc()
    HTTP_LATENCY.labels(method=method, path=label_path).observe(duration_seconds)


def record_planner_outcome(outcome: str) -> None:
    OPENAI_PLANNER_REQUESTS.labels(outcome=outcome).inc()


def record_planner_retry() -> None:
    OPENAI_PLANNER_RETRIES.inc()


def record_circuit_trip() -> None:
    OPENAI_CIRCUIT_STATE.inc()


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
