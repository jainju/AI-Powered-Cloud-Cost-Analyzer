"""Data models for the AWS Resource Detection backend."""

from backend.models.resource import DetectedResource
from backend.models.scan import (
    ErrorResponse,
    HealthResponse,
    ResourceInventory,
    ScanFailure,
    ScanResponse,
    ScanSummary,
)

__all__ = [
    "DetectedResource",
    "ErrorResponse",
    "HealthResponse",
    "ResourceInventory",
    "ScanFailure",
    "ScanResponse",
    "ScanSummary",
]
