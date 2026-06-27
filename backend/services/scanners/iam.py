"""IAM scanner for detecting IAM users and roles."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class IAMScanner(BaseScanner):
    """Scanner for AWS IAM resources.

    IAM is a global service — users and roles are not region-scoped, so this
    scanner runs exactly once regardless of how many regions are configured.
    Handles pagination using the Marker/IsTruncated pattern.
    """

    service_name: str = "iam"
    is_global: bool = True

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan for IAM users and roles.

        Args:
            client: A boto3 IAM client.
            region: The region parameter (unused for IAM since it's global).

        Returns:
            A list of DetectedResource objects for all discovered IAM resources.
        """
        resources: List[DetectedResource] = []

        resources.extend(self._scan_users(client))
        resources.extend(self._scan_roles(client))

        return resources

    def _scan_users(self, client) -> List[DetectedResource]:
        """Scan for IAM users with Marker/IsTruncated pagination.

        Args:
            client: A boto3 IAM client.

        Returns:
            List of DetectedResource objects representing IAM users.
        """
        resources: List[DetectedResource] = []
        params: dict = {}

        while True:
            response = client.list_users(**params)

            for user in response.get("Users", []):
                create_date = user.get("CreateDate")
                created_at = create_date.isoformat() if create_date else None

                resources.append(
                    DetectedResource(
                        resource_id=user["UserName"],
                        resource_type="user",
                        service="iam",
                        region="global",
                        created_at=created_at,
                        state="active",
                    )
                )

            if response.get("IsTruncated", False):
                params["Marker"] = response["Marker"]
            else:
                break

        return resources

    def _scan_roles(self, client) -> List[DetectedResource]:
        """Scan for IAM roles with Marker/IsTruncated pagination.

        Args:
            client: A boto3 IAM client.

        Returns:
            List of DetectedResource objects representing IAM roles.
        """
        resources: List[DetectedResource] = []
        params: dict = {}

        while True:
            response = client.list_roles(**params)

            for role in response.get("Roles", []):
                create_date = role.get("CreateDate")
                created_at = create_date.isoformat() if create_date else None

                resources.append(
                    DetectedResource(
                        resource_id=role["RoleName"],
                        resource_type="role",
                        service="iam",
                        region="global",
                        created_at=created_at,
                        state="active",
                    )
                )

            if response.get("IsTruncated", False):
                params["Marker"] = response["Marker"]
            else:
                break

        return resources
