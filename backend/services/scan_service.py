"""Scan Service manages the scan lifecycle and prevents concurrent scans.

Provides a global asyncio.Lock to ensure only one scan runs at a time,
returning a 429-equivalent error if a scan is already in progress.
"""

import asyncio
import logging

from backend.models.scan import ScanResponse
from backend.services.resource_detector import ResourceDetector

logger = logging.getLogger(__name__)


class ScanInProgressError(Exception):
    """Raised when a scan is requested while another scan is already running."""

    pass


class ScanService:
    """Manages scan lifecycle and prevents concurrent scans.

    Uses an asyncio.Lock to ensure only one scan can run at a time.
    If a scan is already in progress, raises ScanInProgressError.
    """

    def __init__(self, detector: ResourceDetector) -> None:
        """Initialize the scan service.

        Args:
            detector: The ResourceDetector instance that performs the actual scanning.
        """
        self._detector = detector
        self._lock = asyncio.Lock()

    async def run_scan(self) -> ScanResponse:
        """Acquire the scan lock, run detection, and return the response.

        Attempts to acquire the lock without blocking. If the lock is already
        held (another scan is in progress), raises ScanInProgressError.

        Returns:
            A ScanResponse containing detected resources, summary, and failures.

        Raises:
            ScanInProgressError: If a scan is already in progress.
        """
        if self._lock.locked():
            logger.warning("Scan request rejected: a scan is already in progress")
            raise ScanInProgressError("A scan is already in progress")

        async with self._lock:
            logger.info("Starting resource detection scan")
            inventory = await self._detector.detect_all()
            logger.info(
                "Scan completed: %d resources detected across %d regions",
                inventory.summary.total_count,
                len(inventory.summary.regions_scanned),
            )

            return ScanResponse(
                resources=inventory.resources,
                summary=inventory.summary,
                failures=inventory.failures,
            )
