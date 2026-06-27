"""Unit tests for Pydantic data models."""

import json

import pytest

from backend.models.resource import DetectedResource
from backend.models.scan import (
    ErrorResponse,
    HealthResponse,
    ResourceInventory,
    ScanFailure,
    ScanResponse,
    ScanSummary,
)


class TestDetectedResource:
    """Tests for DetectedResource model."""

    def test_create_with_all_fields(self):
        resource = DetectedResource(
            resource_id="i-1234567890abcdef0",
            resource_type="instance",
            service="ec2",
            region="us-east-1",
            created_at="2024-01-15T10:30:00Z",
            state="running",
        )
        assert resource.resource_id == "i-1234567890abcdef0"
        assert resource.resource_type == "instance"
        assert resource.service == "ec2"
        assert resource.region == "us-east-1"
        assert resource.created_at == "2024-01-15T10:30:00Z"
        assert resource.state == "running"

    def test_created_at_defaults_to_none(self):
        resource = DetectedResource(
            resource_id="vol-abc123",
            resource_type="volume",
            service="ec2",
            region="us-west-2",
            state="available",
        )
        assert resource.created_at is None

    def test_created_at_serialized_as_null_in_dict(self):
        resource = DetectedResource(
            resource_id="vol-abc123",
            resource_type="volume",
            service="ec2",
            region="us-west-2",
            state="available",
        )
        data = resource.model_dump()
        assert "created_at" in data
        assert data["created_at"] is None

    def test_created_at_serialized_as_null_in_json(self):
        resource = DetectedResource(
            resource_id="vol-abc123",
            resource_type="volume",
            service="ec2",
            region="us-west-2",
            state="available",
        )
        json_str = resource.model_dump_json()
        parsed = json.loads(json_str)
        assert "created_at" in parsed
        assert parsed["created_at"] is None

    def test_serialization_round_trip(self):
        resource = DetectedResource(
            resource_id="i-abc123",
            resource_type="instance",
            service="ec2",
            region="eu-west-1",
            created_at="2024-03-01T08:00:00Z",
            state="stopped",
        )
        json_str = resource.model_dump_json()
        restored = DetectedResource.model_validate_json(json_str)
        assert restored == resource

    def test_serialization_round_trip_with_none_created_at(self):
        resource = DetectedResource(
            resource_id="snap-xyz789",
            resource_type="snapshot",
            service="ec2",
            region="ap-southeast-1",
            created_at=None,
            state="completed",
        )
        json_str = resource.model_dump_json()
        restored = DetectedResource.model_validate_json(json_str)
        assert restored == resource

    def test_json_schema_has_all_required_fields(self):
        json_str = DetectedResource(
            resource_id="test-id",
            resource_type="test-type",
            service="test-service",
            region="us-east-1",
            state="active",
        ).model_dump_json()
        parsed = json.loads(json_str)
        required_fields = {"resource_id", "resource_type", "service", "region", "created_at", "state"}
        assert set(parsed.keys()) == required_fields


class TestScanFailure:
    """Tests for ScanFailure model."""

    def test_create_scan_failure(self):
        failure = ScanFailure(
            service="rds",
            region="us-east-1",
            error="Access Denied",
        )
        assert failure.service == "rds"
        assert failure.region == "us-east-1"
        assert failure.error == "Access Denied"


class TestScanSummary:
    """Tests for ScanSummary model."""

    def test_create_scan_summary(self):
        summary = ScanSummary(
            total_count=15,
            count_per_service={"ec2": 10, "s3": 5},
            regions_scanned=["us-east-1", "eu-west-1"],
        )
        assert summary.total_count == 15
        assert summary.count_per_service == {"ec2": 10, "s3": 5}
        assert summary.regions_scanned == ["us-east-1", "eu-west-1"]
        assert summary.timed_out is False

    def test_timed_out_defaults_to_false(self):
        summary = ScanSummary(
            total_count=0,
            count_per_service={},
            regions_scanned=["us-east-1"],
        )
        assert summary.timed_out is False

    def test_timed_out_can_be_set_true(self):
        summary = ScanSummary(
            total_count=5,
            count_per_service={"ec2": 5},
            regions_scanned=["us-east-1"],
            timed_out=True,
        )
        assert summary.timed_out is True


class TestResourceInventory:
    """Tests for ResourceInventory model."""

    def test_create_resource_inventory(self):
        resource = DetectedResource(
            resource_id="i-123",
            resource_type="instance",
            service="ec2",
            region="us-east-1",
            state="running",
        )
        failure = ScanFailure(service="s3", region="us-east-1", error="Timeout")
        summary = ScanSummary(
            total_count=1,
            count_per_service={"ec2": 1},
            regions_scanned=["us-east-1"],
        )
        inventory = ResourceInventory(
            resources=[resource],
            failures=[failure],
            summary=summary,
        )
        assert len(inventory.resources) == 1
        assert len(inventory.failures) == 1
        assert inventory.summary.total_count == 1


class TestScanResponse:
    """Tests for ScanResponse model."""

    def test_create_scan_response(self):
        resource = DetectedResource(
            resource_id="bucket-name",
            resource_type="bucket",
            service="s3",
            region="global",
            created_at="2024-01-01T00:00:00Z",
            state="active",
        )
        summary = ScanSummary(
            total_count=1,
            count_per_service={"s3": 1},
            regions_scanned=["us-east-1"],
        )
        response = ScanResponse(resources=[resource], summary=summary)
        assert response.failures == []

    def test_failures_default_to_empty_list(self):
        summary = ScanSummary(
            total_count=0,
            count_per_service={},
            regions_scanned=[],
        )
        response = ScanResponse(resources=[], summary=summary)
        assert response.failures == []


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_create_error_response(self):
        error = ErrorResponse(error="Something went wrong", correlation_id="abc-123")
        assert error.error == "Something went wrong"
        assert error.correlation_id == "abc-123"

    def test_correlation_id_defaults_to_none(self):
        error = ErrorResponse(error="Internal error")
        assert error.correlation_id is None


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_create_health_response(self):
        health = HealthResponse(status="healthy", service="ai-cloud-cost-detective")
        assert health.status == "healthy"
        assert health.service == "ai-cloud-cost-detective"
