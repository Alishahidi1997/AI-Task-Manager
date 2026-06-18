"""HTTP request logging middleware — plain text or JSON lines."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.http")


def http_log_json_enabled() -> bool:
    raw = os.getenv("HTTP_LOG_JSON", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    from app.services.production import is_production

    return is_production()


def format_http_log_line(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> str:
    if http_log_json_enabled():
        payload = {
            "event": "http_request",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return f"{method} {path} -> {status_code} {duration_ms:.1f}ms rid={request_id}"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each HTTP request with method, path, status, duration, and request id."""

    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            format_http_log_line(
                request_id=rid,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        )
        response.headers["X-Request-ID"] = rid
        return response
