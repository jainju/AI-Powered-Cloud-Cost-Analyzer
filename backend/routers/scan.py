"""Scan router for triggering AWS resource detection scans.

Provides the POST /api/v1/resources/scan endpoint that initiates a full
resource detection scan across all configured AWS services and regions.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.models.scan import ScanResponse, ErrorResponse
from backend.services.aws_client import AuthenticationError
from backend.services.scan_service import ScanInProgressError, ScanService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/resources", tags=["scan"])


def _get_correlation_id(request: Request) -> str | None:
    """Extract correlation ID from request state if available."""
    return getattr(request.state, "correlation_id", None)


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(request: Request) -> ScanResponse:
    """Trigger a full resource detection scan.

    Initiates scanning across all configured AWS services and regions.
    Returns detected resources, a summary, and any failures encountered.

    Returns:
        ScanResponse with resources, summary, and failures on success (200).
        ErrorResponse with 401 on authentication failure.
        ErrorResponse with 429 if a scan is already in progress.
        ErrorResponse with 500 on unexpected errors.
    """
    scan_service: ScanService = request.app.state.scan_service

    try:
        result = await scan_service.run_scan()
        return result
    except ScanInProgressError:
        correlation_id = _get_correlation_id(request)
        logger.warning(
            "Scan rejected: already in progress",
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error="A scan is already in progress",
                correlation_id=correlation_id,
            ).model_dump(),
        )
    except AuthenticationError as e:
        correlation_id = _get_correlation_id(request)
        logger.error(
            "Authentication failed: %s",
            str(e),
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=401,
            content=ErrorResponse(
                error=f"AWS authentication failed: {str(e)}",
                correlation_id=correlation_id,
            ).model_dump(),
        )
    except Exception as e:
        correlation_id = _get_correlation_id(request)
        logger.error(
            "Unexpected error during scan: %s",
            str(e),
            exc_info=True,
            extra={"correlation_id": correlation_id},
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="An internal error occurred",
                correlation_id=correlation_id,
            ).model_dump(),
        )
