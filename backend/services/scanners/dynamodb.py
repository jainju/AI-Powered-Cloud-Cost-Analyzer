"""DynamoDB scanner for detecting DynamoDB table resources."""

from typing import List

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class DynamoDBScanner(BaseScanner):
    """Scanner for AWS DynamoDB tables.

    Discovers all DynamoDB tables in a region by listing table names
    and then describing each table to extract metadata.
    """

    service_name = "dynamodb"
    is_global = False

    async def scan(self, client, region: str) -> List[DetectedResource]:
        """Scan the given region for DynamoDB tables.

        Uses list_tables with pagination (ExclusiveStartTableName/LastEvaluatedTableName)
        to retrieve all table names, then calls describe_table for each to get
        creation time and status.

        Args:
            client: A boto3 DynamoDB client configured for the target region.
            region: The AWS region being scanned.

        Returns:
            A list of DetectedResource objects for each DynamoDB table found.
        """
        table_names = await self._list_all_tables(client)
        resources: List[DetectedResource] = []

        for table_name in table_names:
            response = client.describe_table(TableName=table_name)
            table = response["Table"]

            created_at = None
            if "CreationDateTime" in table and table["CreationDateTime"] is not None:
                created_at = table["CreationDateTime"].isoformat()

            resources.append(
                DetectedResource(
                    resource_id=table_name,
                    resource_type="table",
                    service="dynamodb",
                    region=region,
                    created_at=created_at,
                    state=table.get("TableStatus", "UNKNOWN"),
                )
            )

        return resources

    async def _list_all_tables(self, client) -> List[str]:
        """Retrieve all table names handling pagination.

        Uses ExclusiveStartTableName/LastEvaluatedTableName for pagination.

        Args:
            client: A boto3 DynamoDB client.

        Returns:
            A complete list of table names in the region.
        """
        table_names: List[str] = []
        kwargs = {}

        while True:
            response = client.list_tables(**kwargs)
            table_names.extend(response.get("TableNames", []))

            last_evaluated = response.get("LastEvaluatedTableName")
            if last_evaluated is None:
                break
            kwargs["ExclusiveStartTableName"] = last_evaluated

        return table_names
