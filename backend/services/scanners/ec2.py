"""EC2 scanner for detecting EC2 instances, volumes, snapshots, and elastic IPs."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class EC2Scanner(BaseScanner):
    """Scanner for AWS EC2 resources.

    Discovers instances, volumes, snapshots, and elastic IPs in a given region.
    Handles pagination for all EC2 API calls to ensure complete resource detection.
    """

    service_name: str = "ec2"
    is_global: bool = False

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan the given region for all EC2 resource types.

        Args:
            client: A boto3 EC2 client configured for the target region.
            region: The AWS region being scanned.

        Returns:
            A list of DetectedResource objects for all discovered EC2 resources.
        """
        resources: List[DetectedResource] = []

        resources.extend(self._scan_instances(client, region))
        resources.extend(self._scan_volumes(client, region))
        resources.extend(self._scan_snapshots(client, region))
        resources.extend(self._scan_elastic_ips(client, region))

        return resources

    def _scan_instances(self, client, region: str) -> List[DetectedResource]:
        """Scan for EC2 instances with pagination.

        Args:
            client: A boto3 EC2 client.
            region: The AWS region being scanned.

        Returns:
            List of DetectedResource objects representing EC2 instances.
        """
        resources: List[DetectedResource] = []
        paginator = client.get_paginator("describe_instances")

        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    launch_time = instance.get("LaunchTime")
                    created_at = launch_time.isoformat() if launch_time else None

                    resources.append(
                        DetectedResource(
                            resource_id=instance["InstanceId"],
                            resource_type="instance",
                            service="ec2",
                            region=region,
                            created_at=created_at,
                            state=instance.get("State", {}).get("Name", "unknown"),
                        )
                    )

        return resources

    def _scan_volumes(self, client, region: str) -> List[DetectedResource]:
        """Scan for EBS volumes with pagination.

        Args:
            client: A boto3 EC2 client.
            region: The AWS region being scanned.

        Returns:
            List of DetectedResource objects representing EBS volumes.
        """
        resources: List[DetectedResource] = []
        paginator = client.get_paginator("describe_volumes")

        for page in paginator.paginate():
            for volume in page.get("Volumes", []):
                create_time = volume.get("CreateTime")
                created_at = create_time.isoformat() if create_time else None

                resources.append(
                    DetectedResource(
                        resource_id=volume["VolumeId"],
                        resource_type="volume",
                        service="ec2",
                        region=region,
                        created_at=created_at,
                        state=volume.get("State", "unknown"),
                    )
                )

        return resources

    def _scan_snapshots(self, client, region: str) -> List[DetectedResource]:
        """Scan for EBS snapshots with pagination.

        Only scans snapshots owned by the current account.

        Args:
            client: A boto3 EC2 client.
            region: The AWS region being scanned.

        Returns:
            List of DetectedResource objects representing EBS snapshots.
        """
        resources: List[DetectedResource] = []
        paginator = client.get_paginator("describe_snapshots")

        for page in paginator.paginate(OwnerIds=["self"]):
            for snapshot in page.get("Snapshots", []):
                start_time = snapshot.get("StartTime")
                created_at = start_time.isoformat() if start_time else None

                resources.append(
                    DetectedResource(
                        resource_id=snapshot["SnapshotId"],
                        resource_type="snapshot",
                        service="ec2",
                        region=region,
                        created_at=created_at,
                        state=snapshot.get("State", "unknown"),
                    )
                )

        return resources

    def _scan_elastic_ips(self, client, region: str) -> List[DetectedResource]:
        """Scan for elastic IP addresses.

        Elastic IPs do not support pagination as describe_addresses returns
        all addresses in a single response.

        Args:
            client: A boto3 EC2 client.
            region: The AWS region being scanned.

        Returns:
            List of DetectedResource objects representing elastic IPs.
        """
        resources: List[DetectedResource] = []
        response = client.describe_addresses()

        for address in response.get("Addresses", []):
            # Elastic IPs don't have a creation timestamp
            # Determine state based on association
            allocation_id = address.get("AllocationId", address.get("PublicIp", "unknown"))
            state = "associated" if address.get("AssociationId") else "disassociated"

            resources.append(
                DetectedResource(
                    resource_id=allocation_id,
                    resource_type="elastic_ip",
                    service="ec2",
                    region=region,
                    created_at=None,
                    state=state,
                )
            )

        return resources
