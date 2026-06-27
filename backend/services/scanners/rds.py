"""RDS scanner for detecting DB instances and clusters."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class RDSScanner(BaseScanner):
    """Scanner for AWS RDS resources.

    Detects DB instances and DB clusters across configured regions.
    Uses Marker/MaxRecords pagination pattern for both API calls.
    """

    service_name = "rds"
    is_global = False

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan the given region for RDS DB instances and clusters.

        Args:
            client: A boto3 RDS client configured for the target region.
            region: The AWS region being scanned.

        Returns:
            A list of DetectedResource objects for all DB instances and clusters.
        """
        resources: List[DetectedResource] = []

        resources.extend(await self._scan_db_instances(client, region))
        resources.extend(await self._scan_db_clusters(client, region))

        return resources

    async def _scan_db_instances(self, client, region: str) -> List[DetectedResource]:
        """Scan for RDS DB instances with pagination."""
        resources: List[DetectedResource] = []
        marker = None

        while True:
            kwargs = {"MaxRecords": 100}
            if marker:
                kwargs["Marker"] = marker

            response = client.describe_db_instances(**kwargs)

            for instance in response.get("DBInstances", []):
                created_at = None
                if instance.get("InstanceCreateTime"):
                    created_at = instance["InstanceCreateTime"].isoformat()

                resources.append(
                    DetectedResource(
                        resource_id=instance["DBInstanceIdentifier"],
                        resource_type="db_instance",
                        service="rds",
                        region=region,
                        created_at=created_at,
                        state=instance.get("DBInstanceStatus", "unknown"),
                    )
                )

            marker = response.get("Marker")
            if not marker:
                break

        return resources

    async def _scan_db_clusters(self, client, region: str) -> List[DetectedResource]:
        """Scan for RDS DB clusters with pagination."""
        resources: List[DetectedResource] = []
        marker = None

        while True:
            kwargs = {"MaxRecords": 100}
            if marker:
                kwargs["Marker"] = marker

            response = client.describe_db_clusters(**kwargs)

            for cluster in response.get("DBClusters", []):
                created_at = None
                if cluster.get("ClusterCreateTime"):
                    created_at = cluster["ClusterCreateTime"].isoformat()

                resources.append(
                    DetectedResource(
                        resource_id=cluster["DBClusterIdentifier"],
                        resource_type="db_cluster",
                        service="rds",
                        region=region,
                        created_at=created_at,
                        state=cluster.get("Status", "unknown"),
                    )
                )

            marker = response.get("Marker")
            if not marker:
                break

        return resources
