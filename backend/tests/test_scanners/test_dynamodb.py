"""Tests for the DynamoDB scanner."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.models.resource import DetectedResource
from backend.services.scanners.dynamodb import DynamoDBScanner


class TestDynamoDBScannerAttributes:
    """Tests for DynamoDBScanner class attributes."""

    def test_service_name(self):
        """DynamoDBScanner has service_name set to 'dynamodb'."""
        scanner = DynamoDBScanner()
        assert scanner.service_name == "dynamodb"

    def test_is_not_global(self):
        """DynamoDBScanner is a regional service (is_global=False)."""
        scanner = DynamoDBScanner()
        assert scanner.is_global is False


class TestDynamoDBScannerScan:
    """Tests for DynamoDBScanner.scan method."""

    @pytest.mark.asyncio
    async def test_scan_single_table(self):
        """Scan returns a DetectedResource for a single table."""
        scanner = DynamoDBScanner()
        creation_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": ["users-table"],
        }
        client.describe_table.return_value = {
            "Table": {
                "TableName": "users-table",
                "TableStatus": "ACTIVE",
                "CreationDateTime": creation_time,
            }
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        resource = resources[0]
        assert isinstance(resource, DetectedResource)
        assert resource.resource_id == "users-table"
        assert resource.resource_type == "table"
        assert resource.service == "dynamodb"
        assert resource.region == "us-east-1"
        assert resource.created_at == creation_time.isoformat()
        assert resource.state == "ACTIVE"

    @pytest.mark.asyncio
    async def test_scan_multiple_tables(self):
        """Scan returns DetectedResources for multiple tables."""
        scanner = DynamoDBScanner()
        creation_time = datetime(2024, 3, 20, 8, 0, 0, tzinfo=timezone.utc)

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": ["orders", "products", "sessions"],
        }
        client.describe_table.side_effect = [
            {
                "Table": {
                    "TableName": "orders",
                    "TableStatus": "ACTIVE",
                    "CreationDateTime": creation_time,
                }
            },
            {
                "Table": {
                    "TableName": "products",
                    "TableStatus": "ACTIVE",
                    "CreationDateTime": creation_time,
                }
            },
            {
                "Table": {
                    "TableName": "sessions",
                    "TableStatus": "CREATING",
                    "CreationDateTime": creation_time,
                }
            },
        ]

        resources = await scanner.scan(client, "eu-west-1")

        assert len(resources) == 3
        assert resources[0].resource_id == "orders"
        assert resources[1].resource_id == "products"
        assert resources[2].resource_id == "sessions"
        assert resources[2].state == "CREATING"
        for r in resources:
            assert r.region == "eu-west-1"
            assert r.service == "dynamodb"
            assert r.resource_type == "table"

    @pytest.mark.asyncio
    async def test_scan_no_tables(self):
        """Scan returns empty list when no tables exist."""
        scanner = DynamoDBScanner()

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": [],
        }

        resources = await scanner.scan(client, "ap-southeast-1")

        assert resources == []
        client.describe_table.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_handles_pagination(self):
        """Scan retrieves all tables across multiple pages."""
        scanner = DynamoDBScanner()
        creation_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

        client = MagicMock()
        # First page returns tables and a pagination token
        client.list_tables.side_effect = [
            {
                "TableNames": ["table-1", "table-2"],
                "LastEvaluatedTableName": "table-2",
            },
            {
                "TableNames": ["table-3"],
                # No LastEvaluatedTableName means last page
            },
        ]
        client.describe_table.side_effect = [
            {
                "Table": {
                    "TableName": "table-1",
                    "TableStatus": "ACTIVE",
                    "CreationDateTime": creation_time,
                }
            },
            {
                "Table": {
                    "TableName": "table-2",
                    "TableStatus": "ACTIVE",
                    "CreationDateTime": creation_time,
                }
            },
            {
                "Table": {
                    "TableName": "table-3",
                    "TableStatus": "ACTIVE",
                    "CreationDateTime": creation_time,
                }
            },
        ]

        resources = await scanner.scan(client, "us-west-2")

        assert len(resources) == 3
        assert resources[0].resource_id == "table-1"
        assert resources[1].resource_id == "table-2"
        assert resources[2].resource_id == "table-3"

        # Verify pagination was used correctly
        assert client.list_tables.call_count == 2
        # Second call should include ExclusiveStartTableName
        second_call_kwargs = client.list_tables.call_args_list[1][1]
        assert second_call_kwargs["ExclusiveStartTableName"] == "table-2"

    @pytest.mark.asyncio
    async def test_scan_table_without_creation_datetime(self):
        """Scan handles tables where CreationDateTime is missing."""
        scanner = DynamoDBScanner()

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": ["legacy-table"],
        }
        client.describe_table.return_value = {
            "Table": {
                "TableName": "legacy-table",
                "TableStatus": "ACTIVE",
                # No CreationDateTime field
            }
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].created_at is None

    @pytest.mark.asyncio
    async def test_scan_table_with_none_creation_datetime(self):
        """Scan handles tables where CreationDateTime is explicitly None."""
        scanner = DynamoDBScanner()

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": ["null-time-table"],
        }
        client.describe_table.return_value = {
            "Table": {
                "TableName": "null-time-table",
                "TableStatus": "DELETING",
                "CreationDateTime": None,
            }
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].created_at is None
        assert resources[0].state == "DELETING"

    @pytest.mark.asyncio
    async def test_scan_maps_region_correctly(self):
        """Scan uses the provided region in all DetectedResource objects."""
        scanner = DynamoDBScanner()
        creation_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": ["my-table"],
        }
        client.describe_table.return_value = {
            "Table": {
                "TableName": "my-table",
                "TableStatus": "ACTIVE",
                "CreationDateTime": creation_time,
            }
        }

        resources = await scanner.scan(client, "ap-northeast-1")

        assert resources[0].region == "ap-northeast-1"

    @pytest.mark.asyncio
    async def test_scan_missing_table_status_defaults_to_unknown(self):
        """Scan defaults state to UNKNOWN when TableStatus is missing."""
        scanner = DynamoDBScanner()
        creation_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        client = MagicMock()
        client.list_tables.return_value = {
            "TableNames": ["weird-table"],
        }
        client.describe_table.return_value = {
            "Table": {
                "TableName": "weird-table",
                "CreationDateTime": creation_time,
                # No TableStatus
            }
        }

        resources = await scanner.scan(client, "us-east-1")

        assert resources[0].state == "UNKNOWN"
