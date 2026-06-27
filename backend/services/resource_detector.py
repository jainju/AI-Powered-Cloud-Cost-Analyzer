"""Resource Detector orchestrates scanning across all services and regions.

Coordinates per-service scanners with concurrency control, timeout handling,
and error isolation to build a complete ResourceInventory.
"""

import asyncio
import logging
from collections import defaultdict
from typing import List

from backend.config.settings import Settings
from backend.models.resource import DetectedResource
from backend.models.scan import ResourceInventory, ScanFailure, ScanSummary
from backend.services.aws_client import AWSClientFactory
from backend.services.scanners.base import BaseScanner

logger = logging.getLogger(__name__)


class ResourceDetector:
    """Orchestrates scanning across all services and regions.

    Uses asyncio.Semaphore for concurrency limiting, asyncio.to_thread for
    running synchronous boto3 calls in a thread pool, and asyncio.wait_for
    for global timeout enforcement.
    """

    def __init__(
        self,
        client_factory: AWSClientFactory,
        scanners: List[BaseScanner],
        settings: Settings,
    ) -> None:
        """Initialize the resource detector.

        Args:
            client_factory: Factory for creating authenticated boto3 clients.
            scanners: List of scanner instances to use for detection.
            settings: Application settings with concurrency and timeout config.
        """
        self._client_factory = client_factory
        self._scanners = scanners
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_api_calls)

    async def detect_all(self) -> ResourceInventory:
        """Run all scanners with concurrency limiting and timeout.

        Invokes regional scanners once per configured region and global
        scanners exactly once. Uses asyncio.Semaphore for concurrency control,
        asyncio.to_thread for thread pool execution of boto3 calls, and
        asyncio.wait_for for global timeout enforcement.

        Per-service errors are caught and recorded as ScanFailure entries;
        scanning continues for remaining services/regions.

        Returns:
            A ResourceInventory with detected resources, failures, and summary.
        """
        resources: List[DetectedResource] = []
        failures: List[ScanFailure] = []
        regions = self._client_factory.get_valid_regions()
        timed_out = False

        try:
            await asyncio.wait_for(
                self._run_all_scans(resources, failures, regions),
                timeout=self._settings.scan_timeout_seconds,
            )
        except asyncio.TimeoutError:
            timed_out = True
            logger.warning(
                "Scan timed out after %d seconds. Returning partial results "
                "with %d resources detected.",
                self._settings.scan_timeout_seconds,
                len(resources),
            )

        # Build summary aggregation
        count_per_service: dict = defaultdict(int)
        for resource in resources:
            count_per_service[resource.service] += 1

        summary = ScanSummary(
            total_count=len(resources),
            count_per_service=dict(count_per_service),
            regions_scanned=list(regions),
            timed_out=timed_out,
        )

        return ResourceInventory(
            resources=resources,
            failures=failures,
            summary=summary,
        )

    async def _run_all_scans(
        self,
        resources: List[DetectedResource],
        failures: List[ScanFailure],
        regions: List[str],
    ) -> None:
        """Create and run all scan tasks concurrently.

        Args:
            resources: Shared list to accumulate detected resources.
            failures: Shared list to accumulate scan failures.
            regions: List of regions to scan.
        """
        tasks: List[asyncio.Task] = []

        for scanner in self._scanners:
            if scanner.is_global:
                # Global scanners run exactly once, using the default region
                task = asyncio.create_task(
                    self._run_scanner(
                        scanner,
                        self._settings.aws_default_region,
                        resources,
                        failures,
                    )
                )
                tasks.append(task)
            else:
                # Regional scanners run once per configured region
                for region in regions:
                    task = asyncio.create_task(
                        self._run_scanner(scanner, region, resources, failures)
                    )
                    tasks.append(task)

        # Wait for all tasks to complete (or be cancelled on timeout)
        if tasks:
            await asyncio.gather(*tasks)

    async def _run_scanner(
        self,
        scanner: BaseScanner,
        region: str,
        resources: List[DetectedResource],
        failures: List[ScanFailure],
    ) -> None:
        """Run a single scanner with concurrency limiting and error handling.

        Acquires the semaphore before executing, wraps the boto3 call in
        asyncio.to_thread for thread pool execution, and catches any errors
        to record as ScanFailure.

        Args:
            scanner: The scanner instance to run.
            region: The region to scan in.
            resources: Shared list to accumulate detected resources.
            failures: Shared list to accumulate scan failures.
        """
        async with self._semaphore:
            try:
                client = self._client_factory.create_client(
                    scanner.service_name, region
                )
                # Wrap the scanner's scan method in asyncio.to_thread
                # to run synchronous boto3 calls in a thread pool
                result = await asyncio.to_thread(
                    self._run_scanner_sync, scanner, client, region
                )
                resources.extend(result)
            except Exception as e:
                error_message = str(e) if str(e) else type(e).__name__
                logger.error(
                    "Scanner failed for service=%s region=%s: %s",
                    scanner.service_name,
                    region,
                    error_message,
                )
                failures.append(
                    ScanFailure(
                        service=scanner.service_name,
                        region=region,
                        error=error_message,
                    )
                )

    def _run_scanner_sync(
        self, scanner: BaseScanner, client, region: str
    ) -> List[DetectedResource]:
        """Synchronous wrapper to run an async scanner in a thread.

        Since the scanner's scan method is async but internally uses
        synchronous boto3 calls, we create a new event loop in the thread
        to execute it.

        Args:
            scanner: The scanner instance to run.
            client: The boto3 client for the scanner.
            region: The region to scan.

        Returns:
            List of detected resources from this scanner.
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(scanner.scan(client, region))
        finally:
            loop.close()
