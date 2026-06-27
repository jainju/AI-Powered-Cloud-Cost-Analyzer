"""Unit tests for the Scan Service (task 9.2).

Tests the ScanService class including concurrency lock behavior,
successful scan execution, and error propagation.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.models.resource import DetectedResource
from backend.models.scan import (
    ResourceInventory,
    ScanFailure,
    ScanResponse,
    ScanSummary,
)
from backend.services.scan_service import ScanInProgressError, ScanService


def _make_inventory(resources=None, failures=None, timed_out=False):
    """Create a ResourceInventory for testing."""
    resources = resources or []
    failures = failures or []
    count_per_service = {}
    for r in resources:
        count_per_service[r.service] = count_per_service.get(r.service, 0) + 1
    return ResourceInventory(
        resources=resources,
        failures=failures,
        summary=ScanSummary(
            total_count=len(resources),
            count_per_service=count_per_service,
            regions_scanned=["us-east-1"],
            timed_out=timed_out,
        ),
    )


def _make_resource(resource_id="i-123", service="ec2", region="us-east-1"):
    """Create a DetectedResource for testing."""
    return DetectedResource(
        resource_id=resource_id,
        resource_type="instance",
        service=service,
        region=region,
        created_at=None,
        state="running",
    )


class TestScanServiceInit:
    """Test ScanService initialization."""

    def test_init_stores_detector(self):
        """ScanService stores the detector reference."""
        detector = MagicMock()
        service = ScanService(detector)
        assert service._detector is detector

    def test_init_creates_lock(self):
        """ScanService creates an asyncio.Lock."""
        detector = MagicMock()
        service = ScanService(detector)
        assert isinstance(service._lock, asyncio.Lock)


class TestScanServiceRunScan:
    """Test ScanService.run_scan behavior."""

    @pytest.mark.asyncio
    async def test_run_scan_returns_scan_response(self):
        """run_scan returns a ScanResponse with resources and summary."""
        resources = [_make_resource()]
        inventory = _make_inventory(resources=resources)

        detector = MagicMock()
        detector.detect_all = AsyncMock(return_value=inventory)

        service = ScanService(detector)
        result = await service.run_scan()

        assert isinstance(result, ScanResponse)
        assert len(result.resources) == 1
        assert result.resources[0].resource_id == "i-123"
        assert result.summary.total_count == 1

    @pytest.mark.asyncio
    async def test_run_scan_empty_resources(self):
        """run_scan returns empty resources when no resources found."""
        inventory = _make_inventory(resources=[])

        detector = MagicMock()
        detector.detect_all = AsyncMock(return_value=inventory)

        service = ScanService(detector)
        result = await service.run_scan()

        assert isinstance(result, ScanResponse)
        assert result.resources == []
        assert result.summary.total_count == 0

    @pytest.mark.asyncio
    async def test_run_scan_includes_failures(self):
        """run_scan includes failures from the inventory."""
        failures = [ScanFailure(service="ec2", region="us-east-1", error="Access denied")]
        inventory = _make_inventory(failures=failures)

        detector = MagicMock()
        detector.detect_all = AsyncMock(return_value=inventory)

        service = ScanService(detector)
        result = await service.run_scan()

        assert len(result.failures) == 1
        assert result.failures[0].service == "ec2"

    @pytest.mark.asyncio
    async def test_run_scan_calls_detect_all(self):
        """run_scan calls detector.detect_all exactly once."""
        inventory = _make_inventory()

        detector = MagicMock()
        detector.detect_all = AsyncMock(return_value=inventory)

        service = ScanService(detector)
        await service.run_scan()

        detector.detect_all.assert_called_once()


class TestScanServiceConcurrencyLock:
    """Test ScanService concurrent scan prevention."""

    @pytest.mark.asyncio
    async def test_concurrent_scan_raises_error(self):
        """A second scan request raises ScanInProgressError while first is running."""
        detector = MagicMock()

        # Make detect_all take some time
        async def slow_detect():
            await asyncio.sleep(0.5)
            return _make_inventory()

        detector.detect_all = slow_detect

        service = ScanService(detector)

        # Start first scan
        task1 = asyncio.create_task(service.run_scan())
        # Give it a moment to acquire the lock
        await asyncio.sleep(0.05)

        # Second scan should raise ScanInProgressError
        with pytest.raises(ScanInProgressError) as exc_info:
            await service.run_scan()

        assert "already in progress" in str(exc_info.value)

        # Cleanup: wait for first task
        await task1

    @pytest.mark.asyncio
    async def test_scan_lock_released_after_completion(self):
        """After a scan completes, a new scan can be started."""
        inventory = _make_inventory()

        detector = MagicMock()
        detector.detect_all = AsyncMock(return_value=inventory)

        service = ScanService(detector)

        # First scan should succeed
        result1 = await service.run_scan()
        assert isinstance(result1, ScanResponse)

        # Second scan should also succeed (lock released)
        result2 = await service.run_scan()
        assert isinstance(result2, ScanResponse)

    @pytest.mark.asyncio
    async def test_scan_lock_released_after_error(self):
        """If a scan fails with an exception, the lock is released."""
        detector = MagicMock()
        detector.detect_all = AsyncMock(side_effect=RuntimeError("AWS error"))

        service = ScanService(detector)

        # First scan should raise
        with pytest.raises(RuntimeError):
            await service.run_scan()

        # Second scan should not raise ScanInProgressError
        # (it should raise the same RuntimeError, not a lock error)
        detector.detect_all = AsyncMock(return_value=_make_inventory())
        result = await service.run_scan()
        assert isinstance(result, ScanResponse)
