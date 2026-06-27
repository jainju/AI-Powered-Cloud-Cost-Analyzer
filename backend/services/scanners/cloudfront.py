"""CloudFront scanner for detecting CloudFront distributions."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class CloudFrontScanner(BaseScanner):
    """Scanner for AWS CloudFront distributions.

    CloudFront is a global service — distributions are not region-scoped,
    so this scanner runs exactly once regardless of how many regions are configured.
    Handles pagination using Marker/NextMarker in the DistributionList response.
    """

    service_name: str = "cloudfront"
    is_global: bool = True

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan for CloudFront distributions using list_distributions.

        Handles pagination via Marker/NextMarker fields in the DistributionList
        to ensure all distributions are retrieved.

        Args:
            client: A boto3 CloudFront client.
            region: The region parameter (unused for CloudFront since it's global).

        Returns:
            A list of DetectedResource objects representing CloudFront distributions.
        """
        resources: List[DetectedResource] = []
        params: dict = {}

        while True:
            response = client.list_distributions(**params)
            distribution_list = response.get("DistributionList", {})
            items = distribution_list.get("Items", [])

            for distribution in items:
                last_modified = distribution.get("LastModifiedTime")
                created_at = last_modified.isoformat() if last_modified else None

                resources.append(
                    DetectedResource(
                        resource_id=distribution["Id"],
                        resource_type="distribution",
                        service="cloudfront",
                        region="global",
                        created_at=created_at,
                        state=distribution.get("Status", "unknown"),
                    )
                )

            # Check if there are more pages
            if distribution_list.get("IsTruncated", False):
                next_marker = distribution_list.get("NextMarker")
                if next_marker:
                    params["Marker"] = next_marker
                else:
                    break
            else:
                break

        return resources
