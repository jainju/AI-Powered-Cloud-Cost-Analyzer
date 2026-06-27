"""S3 scanner for detecting S3 buckets."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class S3Scanner(BaseScanner):
    """Scanner for AWS S3 buckets.

    S3 is a global service — buckets are not region-scoped, so this scanner
    runs exactly once regardless of how many regions are configured.
    """

    service_name: str = "s3"
    is_global: bool = True

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan for S3 buckets using list_buckets.

        S3 list_buckets returns all buckets in the account in a single
        non-paginated response, so no pagination handling is needed.

        Args:
            client: A boto3 S3 client.
            region: The region parameter (unused for S3 since it's global).

        Returns:
            A list of DetectedResource objects representing S3 buckets.
        """
        response = client.list_buckets()
        buckets = response.get("Buckets", [])

        resources: List[DetectedResource] = []
        for bucket in buckets:
            created_at = None
            creation_date = bucket.get("CreationDate")
            if creation_date is not None:
                created_at = creation_date.isoformat()

            resources.append(
                DetectedResource(
                    resource_id=bucket["Name"],
                    resource_type="bucket",
                    service="s3",
                    region="global",
                    created_at=created_at,
                    state="active",
                )
            )

        return resources
