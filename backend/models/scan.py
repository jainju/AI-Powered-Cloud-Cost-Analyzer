"""Pydantic models for scan responses and related schemas."""

from pydantic import BaseModel
from typing import Dict, List, Optional

from backend.models.resource import DetectedResource


class ScanFailure(BaseModel):
    """Represents a failure encountered during scanning a specific service/region.

    Fields:
        service: The AWS service that failed to scan.
        region: The AWS region where the failure occurred.
        error: A sanitized error description.
    """

    service: str
    region: str
    error: str


class ScanSummary(BaseModel):
    """Summary statistics for a completed resource scan.

    Fields:
        total_count: Total number of resources detected.
        count_per_service: Mapping of service name to resource count.
        regions_scanned: List of regions that were scanned.
        timed_out: Whether the scan exceeded the timeout limit.
    """

    total_count: int
    count_per_service: Dict[str, int]
    regions_scanned: List[str]
    timed_out: bool = False


class ResourceInventory(BaseModel):
    """Complete inventory of detected resources, failures, and summary.

    Fields:
        resources: List of all detected resources.
        failures: List of scan failures encountered.
        summary: Aggregated scan summary statistics.
    """

    resources: List[DetectedResource]
    failures: List[ScanFailure]
    summary: ScanSummary


class ScanResponse(BaseModel):
    """API response model for the scan endpoint.

    Fields:
        resources: List of all detected resources.
        summary: Aggregated scan summary statistics.
        failures: List of scan failures encountered (may be empty).
    """

    resources: List[DetectedResource]
    summary: ScanSummary
    failures: List[ScanFailure] = []


class ErrorResponse(BaseModel):
    """API error response model.

    Fields:
        error: A human-readable error description.
        correlation_id: The request correlation ID for tracing.
    """

    error: str
    correlation_id: Optional[str] = None


class HealthResponse(BaseModel):
    """API health check response model.

    Fields:
        status: The health status (e.g., 'healthy').
        service: The service name identifier.
    """

    status: str
    service: str
