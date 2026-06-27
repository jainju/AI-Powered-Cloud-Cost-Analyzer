"""Correlation ID middleware for request tracing.

Generates a unique UUID per incoming request, stores it in the request state,
and makes it available via a context variable for injection into log entries
throughout request processing.

Requirements: 7.4, 7.5
"""

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.exceptions import ScanInProgressError
from backend.services.aws_client import AuthenticationError

logger = logging.getLogger(__name__)

# Context variable to hold the correlation ID for the current request.
# Accessible from anywhere in the async call chain during request processing.
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


def get_correlation_id() -> Optional[str]:
    """Get the current request's correlation ID from the context variable.

    Returns:
        The correlation ID string if within a request context, None otherwise.
    """
    return correlation_id_ctx.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that generates and propagates a correlation ID per request.

    For each incoming request:
    1. Generates a new UUID4 as the correlation ID
    2. Sets it in a context variable (available to all async code in the request)
    3. Stores it in request.state for access in route handlers
    4. Adds it to the response headers as X-Correlation-ID
    5. Catches unhandled exceptions and returns sanitized error responses
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate a unique correlation ID for this request
        request_correlation_id = str(uuid.uuid4())

        # Store in context variable for access throughout the request lifecycle
        # (used by structured logging to inject into all log entries)
        token = correlation_id_ctx.set(request_correlation_id)

        try:
            # Store in request state for access in route handlers
            request.state.correlation_id = request_correlation_id

            # Process the request
            response = await call_next(request)

            # Include correlation ID in response headers for client traceability
            response.headers["X-Correlation-ID"] = request_correlation_id

            return response
        except AuthenticationError as exc:
            logger.error(
                "Authentication error: %s",
                str(exc),
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": str(exc),
                    "correlation_id": request_correlation_id,
                },
                headers={"X-Correlation-ID": request_correlation_id},
            )
        except ScanInProgressError as exc:
            logger.warning(
                "Scan in progress: %s",
                exc.message,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": exc.message,
                    "correlation_id": request_correlation_id,
                },
                headers={"X-Correlation-ID": request_correlation_id},
            )
        except ValidationError:
            logger.error("Response validation error")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal response error",
                    "correlation_id": request_correlation_id,
                },
                headers={"X-Correlation-ID": request_correlation_id},
            )
        except Exception:
            logger.error(
                "Unhandled exception occurred",
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "An internal error occurred",
                    "correlation_id": request_correlation_id,
                },
                headers={"X-Correlation-ID": request_correlation_id},
            )
        finally:
            # Reset the context variable to avoid leaking between requests
            correlation_id_ctx.reset(token)
