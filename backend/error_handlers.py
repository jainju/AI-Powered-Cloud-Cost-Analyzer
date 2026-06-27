"""Global exception handlers for the FastAPI application.

Registers exception handlers that map application exceptions to appropriate
HTTP responses with sanitized error messages and correlation IDs.
No stack traces, file paths, or internal class names are exposed.

Requirements: 4.6, 4.7, 5.3, 7.5
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.exceptions import ScanInProgressError
from backend.middleware.correlation import get_correlation_id
from backend.services.aws_client import AuthenticationError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        """Handle AWS authentication failures.

        Maps AuthenticationError to a 401 response with the failure reason.
        """
        correlation_id = get_correlation_id()
        logger.error(
            "Authentication error: %s",
            str(exc),
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": str(exc),
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(ScanInProgressError)
    async def scan_in_progress_error_handler(
        request: Request, exc: ScanInProgressError
    ) -> JSONResponse:
        """Handle concurrent scan requests.

        Maps ScanInProgressError to a 429 response.
        """
        correlation_id = get_correlation_id()
        logger.warning(
            "Scan in progress: %s",
            exc.message,
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": exc.message,
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors on output serialization.

        Maps ValidationError to a 500 response with a generic message.
        No internal model details are exposed.
        """
        correlation_id = get_correlation_id()
        logger.error(
            "Response validation error",
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal response error",
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle any unhandled exceptions.

        Maps all unexpected exceptions to a 500 response with a generic
        description and correlation ID. No stack traces, file paths, or
        internal class names are exposed.
        """
        correlation_id = get_correlation_id()
        logger.error(
            "Unhandled exception occurred",
            exc_info=True,
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "An internal error occurred",
                "correlation_id": correlation_id,
            },
        )
