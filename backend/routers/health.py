"""Health check router for the AI Cloud Cost Detective service."""

from fastapi import APIRouter

from backend.models.scan import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health status.

    Returns a 200 response indicating the service is healthy and operational.
    """
    return HealthResponse(status="healthy", service="ai-cloud-cost-detective")
