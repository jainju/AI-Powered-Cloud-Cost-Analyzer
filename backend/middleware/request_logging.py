"""Request logging middleware.

Logs request method, path, response status code, and response time
in milliseconds at INFO level using the structured logging configuration.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.config.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that logs request/response details at INFO level."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Log request method, path, status code, and response time in ms."""
        start_time = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "%s %s %d %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response
