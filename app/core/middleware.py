"""
CORS, structured logging and rate limiting middleware.
"""
import time
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
import structlog

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration, 2),
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-process sliding window rate limiter (per client IP)."""

    def __init__(self, app, max_requests: int = 200, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds
        bucket = self._buckets[client_ip]

        # Purge old timestamps
        self._buckets[client_ip] = [t for t in bucket if t > window_start]

        if len(self._buckets[client_ip]) >= self.max_requests:
            return Response(
                content='{"detail":"Too many requests"}',
                status_code=429,
                media_type="application/json",
            )

        self._buckets[client_ip].append(now)
        return await call_next(request)
