import time

from starlette.middleware.base import BaseHTTPMiddleware

from app.metrics.prometheus import record_http_request


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        record_http_request(request.method, request.url.path, response.status_code, duration)
        return response
