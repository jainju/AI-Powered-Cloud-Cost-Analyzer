"""Tests for the S3 scanner."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.models.resource import DetectedResource
from backend.services.scanners.s3 import S3Scanner


class TestS3Scanner:
    """Tests for S3Scanner class."""

    def test_service_name_is_s3(self):
        """S3Scanner has service_name set to 's3'."""
        scanner = S3Scanner()
        assert scanner.service_name == "s3"

    def test_is_global(self):
        """S3Scanner is a global service scanner."""
        scanner = S3Scanner()
        assert scanner.is_global is True

    @pytest.mark.asyncio
    async def test_scan_returns_buckets(self):
        """scan returns DetectedResource objects for each bucket."""
        creation_date = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        client = MagicMock()
        client.list_buckets.return_value = {
            "Buckets": [
                {"Name": "my-app-bucket", "CreationDate": creation_date},
                {"Name": "logs-bucket", "CreationDate": creation_date},
            ],
            "Owner": {"DisplayName": "owner", "ID": "abc123"},
        }

        scanner = S3Scanner()
        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 2
        assert all(isinstance(r, DetectedResource) for r in resources)

        # Check first bucket
        assert resources[0].resource_id == "my-app-bucket"
        assert resources[0].resource_type == "bucket"
        assert resources[0].service == "s3"
        assert resources[0].region == "global"
        assert resources[0].state == "active"
        assert resources[0].created_at == creation_date.isoformat()

        # Check second bucket
        assert resources[1].resource_id == "logs-bucket"

    @pytest.mark.asyncio
    async def test_scan_empty_buckets(self):
        """scan returns empty list when no buckets exist."""
        client = MagicMock()
        client.list_buckets.return_value = {"Buckets": [], "Owner": {}}

        scanner = S3Scanner()
        resources = await scanner.scan(client, "us-east-1")

        assert resources == []

    @pytest.mark.asyncio
    async def test_scan_missing_buckets_key(self):
        """scan handles response missing 'Buckets' key gracefully."""
        client = MagicMock()
        client.list_buckets.return_value = {}

        scanner = S3Scanner()
        resources = await scanner.scan(client, "us-east-1")

        assert resources == []

    @pytest.mark.asyncio
    async def test_scan_bucket_without_creation_date(self):
        """scan handles bucket with no CreationDate, setting created_at to None."""
        client = MagicMock()
        client.list_buckets.return_value = {
            "Buckets": [{"Name": "no-date-bucket"}]
        }

        scanner = S3Scanner()
        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "no-date-bucket"
        assert resources[0].created_at is None

    @pytest.mark.asyncio
    async def test_scan_region_parameter_ignored(self):
        """scan always sets region to 'global' regardless of input region."""
        client = MagicMock()
        client.list_buckets.return_value = {
            "Buckets": [
                {"Name": "bucket-1", "CreationDate": datetime(2023, 1, 1, tzinfo=timezone.utc)}
            ]
        }

        scanner = S3Scanner()
        resources = await scanner.scan(client, "eu-west-1")

        assert resources[0].region == "global"

    @pytest.mark.asyncio
    async def test_scan_created_at_is_iso_8601(self):
        """scan converts CreationDate to ISO 8601 string."""
        creation_date = datetime(2024, 3, 20, 14, 45, 30, tzinfo=timezone.utc)
        client = MagicMock()
        client.list_buckets.return_value = {
            "Buckets": [{"Name": "test-bucket", "CreationDate": creation_date}]
        }

        scanner = S3Scanner()
        resources = await scanner.scan(client, "us-east-1")

        assert resources[0].created_at == "2024-03-20T14:45:30+00:00"
