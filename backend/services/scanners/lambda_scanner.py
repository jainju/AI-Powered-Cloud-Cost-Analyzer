"""AWS Lambda service scanner."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class LambdaScanner(BaseScanner):
    """Scanner for AWS Lambda functions.

    Discovers all Lambda functions in a given region using the list_functions API.
    Handles pagination via Marker/NextMarker pattern.
    """

    service_name = "lambda"
    is_global = False

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan the given region for Lambda functions.

        Args:
            client: A boto3 Lambda client configured for the target region.
            region: The AWS region being scanned.

        Returns:
            A list of DetectedResource objects representing discovered Lambda functions.
        """
        resources: List[DetectedResource] = []
        params: dict = {}

        while True:
            response = client.list_functions(**params)
            functions = response.get("Functions", [])

            for func in functions:
                # Determine state: Lambda uses State field, default to "active"
                state = func.get("State", "active")

                # LastModified is an ISO 8601 timestamp string
                created_at = func.get("LastModified")

                resources.append(
                    DetectedResource(
                        resource_id=func["FunctionName"],
                        resource_type="function",
                        service="lambda",
                        region=region,
                        created_at=created_at,
                        state=state,
                    )
                )

            # Handle pagination using Marker/NextMarker pattern
            next_marker = response.get("NextMarker")
            if next_marker:
                params["Marker"] = next_marker
            else:
                break

        return resources
