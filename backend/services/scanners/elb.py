"""ELB scanner for detecting Elastic Load Balancers (ELBv2)."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class ELBScanner(BaseScanner):
    """Scanner for AWS Elastic Load Balancers (ELBv2).

    Discovers Application, Network, and Gateway load balancers in a given region
    using the ELBv2 API. Handles pagination via Marker/NextMarker pattern.
    """

    service_name: str = "elb"
    is_global: bool = False

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan the given region for load balancers.

        Uses describe_load_balancers from the ELBv2 API with Marker-based
        pagination to retrieve all load balancers in the region.

        Args:
            client: A boto3 ELBv2 client configured for the target region.
            region: The AWS region being scanned.

        Returns:
            A list of DetectedResource objects representing load balancers.
        """
        resources: List[DetectedResource] = []
        marker = None

        while True:
            kwargs = {}
            if marker is not None:
                kwargs["Marker"] = marker

            response = client.describe_load_balancers(**kwargs)

            for lb in response.get("LoadBalancers", []):
                created_time = lb.get("CreatedTime")
                created_at = created_time.isoformat() if created_time else None

                state = lb.get("State", {}).get("Code", "unknown")

                resources.append(
                    DetectedResource(
                        resource_id=lb["LoadBalancerName"],
                        resource_type="load_balancer",
                        service="elb",
                        region=region,
                        created_at=created_at,
                        state=state,
                    )
                )

            marker = response.get("NextMarker")
            if not marker:
                break

        return resources
