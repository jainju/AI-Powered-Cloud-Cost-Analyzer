"""Base scanner interface for AWS service scanners."""

from abc import ABC, abstractmethod
from typing import List

from backend.models.resource import DetectedResource


class BaseScanner(ABC):
    """Base class for all AWS service scanners.

    Each scanner targets a specific AWS service and implements the scan method
    to discover resources of that service type.

    Class Attributes:
        service_name: The AWS service name this scanner targets (e.g., 'ec2', 's3').
        is_global: Whether this is a global service. Global services (S3, CloudFront,
            IAM) are scanned exactly once regardless of configured regions. Regional
            services are scanned once per configured region.
    """

    service_name: str
    is_global: bool = False

    @abstractmethod
    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan the given region for resources of this service type.

        Must handle pagination internally to retrieve all resources.

        Args:
            client: A boto3 client configured for the appropriate service and region.
            region: The AWS region being scanned.

        Returns:
            A list of DetectedResource objects representing discovered resources.
        """
        ...
