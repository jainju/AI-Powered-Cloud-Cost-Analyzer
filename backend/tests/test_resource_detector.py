"""Unit tests for the Resource Detector (task 6.1).

Tests concurrency control, timeout handling, error isolation,
and summary aggregation in the ResourceDetector class.
"""

import asyncio
import os
import sys
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.config.settings import Settings
from backend.models.resource import DetectedResource
from backend.services.aws_client import AWSClientFactory
from backend.services.resource_detector import ResourceDetector
from backend.services.scanners.base import BaseScanner


def _make_settings(**overrides):
    """Create a Settings instance with valid defaults for testing."""
    defaults = {
        "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_default_region": "us-east-1",
        "aws_regions": ["us-east-1", "eu-west-1"],
        "max_concurrent_api_calls": 10,
        "scan_timeout_seconds": 300,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class MockRegionalScanner(BaseScanner):
    """A mock regional scanner that returns preconfigured resources."""

    service_name: str = "ec2"
    is_global: bool = False

    def __init__(self, service_name: str = "ec2", resources=None, error=None):
        self.service_name = service_name
        self._resources = resources or []
        self._error = error
        self.scan_calls = []

    async def scan(self, client, region: str) -> List[DetectedResource]:
        self.scan_calls.append((client, region))
        if self._error:
            raise self._error
        return self._resources


class MockGlobalScanner(BaseScanner):
    """A mock global scanner that returns preconfigured resources."""

    service_name: str = "s3"
    is_global: bool = True

    def __init__(self, service_name: str = "s3", resources=None, error=None):
        self.service_name = service_name
        self._resources = resources or []
        self._error = error
        self.scan_calls = []

    async def scan(self, client, region: str) -> List[DetectedResource]:
        self.scan_calls.append((client, region))
        if self._error:
            raise self._error
        return self._resources


class SlowScanner(BaseScanner):
    """A scanner that takes a long time to complete, for timeout testing."""

    service_name: str = "slow"
    is_global: bool = False

    def __init__(self, delay: float = 10.0):
        self._delay = delay
        self.scan_calls = []

    async def scan(self, client, region: str) -> List[DetectedResource]:
        self.scan_calls.append((client, region))
        await asyncio.sleep(self._delay)
        return [
            DetectedResource(
                resource_id="slow-1",
                resource_type="instance",
                service="slow",
                region=region,
                created_at=None,
                state="running",
            )
        ]


def _make_resource(service: str, region: str, resource_id: str) -> DetectedResource:
    """Helper to create a DetectedResource for testing."""
    return DetectedResource(
        resource_id=resource_id,
        resource_type="instance",
        service=service,
        region=region,
        created_at=None,
        state="running",
    )


@pytest.fixture
def mock_client_factory():
    """Create a mock AWSClientFactory."""
    factory = MagicMock(spec=AWSClientFactory)
    factory.get_valid_regions.return_value = ["us-east-1", "eu-west-1"]
    factory.create_client.return_value = MagicMock()
    return factory


class TestResourceDetectorInit:
    """Test ResourceDetector initialization."""

    def test_init_stores_dependencies(self, mock_client_factory):
        """ResourceDetector stores client_factory, scanners, and settings."""
        settings = _make_settings()
        scanners = [MockRegionalScanner()]
        detector = ResourceDetector(mock_client_factory, scanners, settings)
        assert detector._client_factory is mock_client_factory
        assert detector._scanners is scanners
        assert detector._settings is settings

    def test_init_creates_semaphore_with_configured_limit(self, mock_client_factory):
        """ResourceDetector creates a semaphore with max_concurrent_api_calls."""
        settings = _make_settings(max_concurrent_api_calls=5)
        detector = ResourceDetector(mock_client_factory, [], settings)
        assert detector._semaphore._value == 5


class TestDetectAllRegionalScanners:
    """Test detect_all with regional scanners."""

    @pytest.mark.asyncio
    async def test_regional_scanner_invoked_once_per_region(self, mock_client_factory):
        """Regional scanners are invoked once per configured region."""
        settings = _make_settings(aws_regions=["us-east-1", "eu-west-1", "ap-southeast-1"])
        mock_client_factory.get_valid_regions.return_value = [
            "us-east-1", "eu-west-1", "ap-southeast-1"
        ]
        scanner = MockRegionalScanner(service_name="ec2")
        detector = ResourceDetector(mock_client_factory, [scanner], settings)

        await detector.detect_all()

        # Scanner should be called 3 times (once per region)
        regions_scanned = [call[1] for call in scanner.scan_calls]
        assert sorted(regions_scanned) == ["ap-southeast-1", "eu-west-1", "us-east-1"]

    @pytest.mark.asyncio
    async def test_regional_scanner_resources_collected(self, mock_client_factory):
        """Resources from regional scanners are aggregated in the inventory."""
        resources = [_make_resource("ec2", "us-east-1", "i-123")]
        scanner = MockRegionalScanner(service_name="ec2", resources=resources)
        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert len(inventory.resources) == 1
        assert inventory.resources[0].resource_id == "i-123"


class TestDetectAllGlobalScanners:
    """Test detect_all with global scanners."""

    @pytest.mark.asyncio
    async def test_global_scanner_invoked_exactly_once(self, mock_client_factory):
        """Global scanners are invoked exactly once regardless of region count."""
        settings = _make_settings(aws_regions=["us-east-1", "eu-west-1", "ap-southeast-1"])
        mock_client_factory.get_valid_regions.return_value = [
            "us-east-1", "eu-west-1", "ap-southeast-1"
        ]
        scanner = MockGlobalScanner(service_name="s3")
        detector = ResourceDetector(mock_client_factory, [scanner], settings)

        await detector.detect_all()

        # Global scanner should only be called once
        assert len(scanner.scan_calls) == 1

    @pytest.mark.asyncio
    async def test_global_scanner_uses_default_region(self, mock_client_factory):
        """Global scanners use the default region for the client."""
        settings = _make_settings(
            aws_default_region="us-east-1",
            aws_regions=["eu-west-1", "ap-southeast-1"],
        )
        mock_client_factory.get_valid_regions.return_value = ["eu-west-1", "ap-southeast-1"]
        scanner = MockGlobalScanner(service_name="s3")
        detector = ResourceDetector(mock_client_factory, [scanner], settings)

        await detector.detect_all()

        # Should use default region
        _, region = scanner.scan_calls[0]
        assert region == "us-east-1"

    @pytest.mark.asyncio
    async def test_global_scanner_resources_collected(self, mock_client_factory):
        """Resources from global scanners are included in the inventory."""
        resources = [_make_resource("s3", "global", "my-bucket")]
        scanner = MockGlobalScanner(service_name="s3", resources=resources)
        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert len(inventory.resources) == 1
        assert inventory.resources[0].resource_id == "my-bucket"


class TestDetectAllMixed:
    """Test detect_all with mixed regional and global scanners."""

    @pytest.mark.asyncio
    async def test_mixed_scanners_correct_invocation_counts(self, mock_client_factory):
        """Regional scanners called N times, global scanners called once."""
        settings = _make_settings(aws_regions=["us-east-1", "eu-west-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1", "eu-west-1"]

        regional = MockRegionalScanner(service_name="ec2")
        global_s = MockGlobalScanner(service_name="s3")

        detector = ResourceDetector(
            mock_client_factory, [regional, global_s], settings
        )
        await detector.detect_all()

        assert len(regional.scan_calls) == 2  # 2 regions
        assert len(global_s.scan_calls) == 1  # global, once only

    @pytest.mark.asyncio
    async def test_no_scanners_returns_empty_inventory(self, mock_client_factory):
        """detect_all with no scanners returns empty inventory."""
        settings = _make_settings()
        detector = ResourceDetector(mock_client_factory, [], settings)
        inventory = await detector.detect_all()

        assert inventory.resources == []
        assert inventory.failures == []
        assert inventory.summary.total_count == 0
        assert inventory.summary.count_per_service == {}


class TestDetectAllErrorHandling:
    """Test per-service error handling in detect_all."""

    @pytest.mark.asyncio
    async def test_scanner_error_recorded_as_failure(self, mock_client_factory):
        """A scanner exception is recorded as a ScanFailure."""
        scanner = MockRegionalScanner(
            service_name="ec2", error=RuntimeError("Access denied")
        )
        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert len(inventory.failures) == 1
        assert inventory.failures[0].service == "ec2"
        assert inventory.failures[0].region == "us-east-1"
        assert "Access denied" in inventory.failures[0].error

    @pytest.mark.asyncio
    async def test_scanner_error_does_not_block_others(self, mock_client_factory):
        """A failing scanner does not prevent other scanners from completing."""
        failing_scanner = MockRegionalScanner(
            service_name="ec2", error=RuntimeError("Permission denied")
        )
        resources = [_make_resource("rds", "us-east-1", "db-123")]
        success_scanner = MockRegionalScanner(
            service_name="rds", resources=resources
        )
        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(
            mock_client_factory, [failing_scanner, success_scanner], settings
        )
        inventory = await detector.detect_all()

        assert len(inventory.failures) == 1
        assert len(inventory.resources) == 1
        assert inventory.resources[0].resource_id == "db-123"

    @pytest.mark.asyncio
    async def test_multiple_failures_across_regions(self, mock_client_factory):
        """Failures in multiple regions are all recorded."""
        scanner = MockRegionalScanner(
            service_name="ec2", error=RuntimeError("Throttled")
        )
        settings = _make_settings(aws_regions=["us-east-1", "eu-west-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1", "eu-west-1"]

        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert len(inventory.failures) == 2
        failure_regions = {f.region for f in inventory.failures}
        assert failure_regions == {"us-east-1", "eu-west-1"}


class TestDetectAllTimeout:
    """Test timeout handling in detect_all."""

    @pytest.mark.asyncio
    async def test_timeout_sets_timed_out_flag(self, mock_client_factory):
        """When scan exceeds timeout, summary.timed_out is True."""
        scanner = SlowScanner(delay=10.0)
        settings = _make_settings(
            aws_regions=["us-east-1"],
            scan_timeout_seconds=1,  # 1 second timeout
        )
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert inventory.summary.timed_out is True

    @pytest.mark.asyncio
    async def test_timeout_preserves_partial_results(self, mock_client_factory):
        """On timeout, resources collected before timeout are preserved."""
        # Create a fast scanner and a slow scanner
        fast_resources = [_make_resource("ec2", "us-east-1", "i-fast")]

        class FastThenSlowScanner(BaseScanner):
            service_name: str = "ec2"
            is_global: bool = False

            async def scan(self, client, region: str) -> List[DetectedResource]:
                return fast_resources

        slow_scanner = SlowScanner(delay=10.0)
        fast_scanner = FastThenSlowScanner()

        settings = _make_settings(
            aws_regions=["us-east-1"],
            scan_timeout_seconds=2,
        )
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(
            mock_client_factory, [fast_scanner, slow_scanner], settings
        )
        inventory = await detector.detect_all()

        # Fast scanner results should be preserved
        assert inventory.summary.timed_out is True
        # The fast scanner should have completed before timeout
        assert any(r.resource_id == "i-fast" for r in inventory.resources)


class TestDetectAllSummaryAggregation:
    """Test summary aggregation in detect_all."""

    @pytest.mark.asyncio
    async def test_total_count_matches_resource_count(self, mock_client_factory):
        """summary.total_count equals the number of resources in the inventory."""
        resources_ec2 = [
            _make_resource("ec2", "us-east-1", "i-1"),
            _make_resource("ec2", "us-east-1", "i-2"),
        ]
        resources_s3 = [_make_resource("s3", "global", "bucket-1")]

        ec2_scanner = MockRegionalScanner(service_name="ec2", resources=resources_ec2)
        s3_scanner = MockGlobalScanner(service_name="s3", resources=resources_s3)

        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(
            mock_client_factory, [ec2_scanner, s3_scanner], settings
        )
        inventory = await detector.detect_all()

        assert inventory.summary.total_count == 3

    @pytest.mark.asyncio
    async def test_count_per_service_correct(self, mock_client_factory):
        """summary.count_per_service correctly tallies resources per service."""
        resources_ec2 = [
            _make_resource("ec2", "us-east-1", "i-1"),
            _make_resource("ec2", "us-east-1", "i-2"),
        ]
        resources_s3 = [_make_resource("s3", "global", "bucket-1")]

        ec2_scanner = MockRegionalScanner(service_name="ec2", resources=resources_ec2)
        s3_scanner = MockGlobalScanner(service_name="s3", resources=resources_s3)

        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        detector = ResourceDetector(
            mock_client_factory, [ec2_scanner, s3_scanner], settings
        )
        inventory = await detector.detect_all()

        assert inventory.summary.count_per_service == {"ec2": 2, "s3": 1}

    @pytest.mark.asyncio
    async def test_regions_scanned_lists_all_configured_regions(self, mock_client_factory):
        """summary.regions_scanned includes all configured regions."""
        settings = _make_settings(aws_regions=["us-east-1", "eu-west-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1", "eu-west-1"]

        scanner = MockRegionalScanner(service_name="ec2")
        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert sorted(inventory.summary.regions_scanned) == ["eu-west-1", "us-east-1"]

    @pytest.mark.asyncio
    async def test_timed_out_false_on_normal_completion(self, mock_client_factory):
        """summary.timed_out is False when scan completes within timeout."""
        settings = _make_settings(aws_regions=["us-east-1"])
        mock_client_factory.get_valid_regions.return_value = ["us-east-1"]

        scanner = MockRegionalScanner(service_name="ec2")
        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        inventory = await detector.detect_all()

        assert inventory.summary.timed_out is False


class TestDetectAllConcurrency:
    """Test concurrency control in detect_all."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_execution(self, mock_client_factory):
        """At most max_concurrent_api_calls scanners execute simultaneously."""
        max_concurrent = 2
        concurrency_tracker = {"current": 0, "max_seen": 0}

        class TrackingScanner(BaseScanner):
            service_name: str = "ec2"
            is_global: bool = False

            async def scan(self, client, region: str) -> List[DetectedResource]:
                concurrency_tracker["current"] += 1
                if concurrency_tracker["current"] > concurrency_tracker["max_seen"]:
                    concurrency_tracker["max_seen"] = concurrency_tracker["current"]
                await asyncio.sleep(0.1)
                concurrency_tracker["current"] -= 1
                return []

        settings = _make_settings(
            aws_regions=["us-east-1", "eu-west-1", "ap-southeast-1", "us-west-2"],
            max_concurrent_api_calls=max_concurrent,
        )
        mock_client_factory.get_valid_regions.return_value = [
            "us-east-1", "eu-west-1", "ap-southeast-1", "us-west-2"
        ]

        scanner = TrackingScanner()
        detector = ResourceDetector(mock_client_factory, [scanner], settings)
        await detector.detect_all()

        assert concurrency_tracker["max_seen"] <= max_concurrent
