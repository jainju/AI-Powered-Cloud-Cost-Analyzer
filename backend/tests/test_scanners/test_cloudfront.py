"""Unit tests for the CloudFront scanner."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.models.resource import DetectedResource
from backend.services.scanners.cloudfront import CloudFrontScanner


@pytest.fixture
def cloudfront_scanner():
    """Create a CloudFrontScanner instance."""
    return CloudFrontScanner()


@pytest.fixture
def mock_cloudfront_client():
    """Create a mock CloudFront client."""
    client = MagicMock()
    return client


class TestCloudFrontScannerAttributes:
    """Tests for CloudFrontScanner class attributes."""

    def test_service_name(self, cloudfront_scanner):
        assert cloudfront_scanner.service_name == "cloudfront"

    def test_is_global(self, cloudfront_scanner):
        assert cloudfront_scanner.is_global is True


class TestScanDistributions:
    """Tests for CloudFront distribution scanning."""

    @pytest.mark.asyncio
    async def test_scan_single_distribution(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning a single CloudFront distribution."""
        last_modified = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [
                    {
                        "Id": "E1234567890ABC",
                        "Status": "Deployed",
                        "LastModifiedTime": last_modified,
                    }
                ],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "E1234567890ABC"
        assert resources[0].resource_type == "distribution"
        assert resources[0].service == "cloudfront"
        assert resources[0].region == "global"
        assert resources[0].created_at == last_modified.isoformat()
        assert resources[0].state == "Deployed"

    @pytest.mark.asyncio
    async def test_scan_multiple_distributions(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning multiple distributions in a single page."""
        last_modified = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [
                    {
                        "Id": "E111111111111",
                        "Status": "Deployed",
                        "LastModifiedTime": last_modified,
                    },
                    {
                        "Id": "E222222222222",
                        "Status": "InProgress",
                        "LastModifiedTime": last_modified,
                    },
                ],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "E111111111111"
        assert resources[0].state == "Deployed"
        assert resources[1].resource_id == "E222222222222"
        assert resources[1].state == "InProgress"

    @pytest.mark.asyncio
    async def test_scan_with_pagination(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning distributions with pagination using Marker/NextMarker."""
        last_modified = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        # First call returns truncated results with NextMarker
        # Second call returns remaining results
        mock_cloudfront_client.list_distributions.side_effect = [
            {
                "DistributionList": {
                    "IsTruncated": True,
                    "NextMarker": "E222222222222",
                    "Items": [
                        {
                            "Id": "E111111111111",
                            "Status": "Deployed",
                            "LastModifiedTime": last_modified,
                        }
                    ],
                }
            },
            {
                "DistributionList": {
                    "IsTruncated": False,
                    "Items": [
                        {
                            "Id": "E222222222222",
                            "Status": "Deployed",
                            "LastModifiedTime": last_modified,
                        }
                    ],
                }
            },
        ]

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "E111111111111"
        assert resources[1].resource_id == "E222222222222"

        # Verify Marker was passed on second call
        calls = mock_cloudfront_client.list_distributions.call_args_list
        assert len(calls) == 2
        assert calls[0] == ((), {})  # First call has no Marker
        assert calls[1] == ((), {"Marker": "E222222222222"})  # Second call uses NextMarker

    @pytest.mark.asyncio
    async def test_scan_empty_distributions(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning when no distributions exist."""
        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert resources == []

    @pytest.mark.asyncio
    async def test_scan_no_items_key(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning when DistributionList has no Items key (empty account)."""
        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert resources == []

    @pytest.mark.asyncio
    async def test_scan_no_last_modified_time(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning a distribution without LastModifiedTime."""
        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [
                    {
                        "Id": "E999999999999",
                        "Status": "Deployed",
                    }
                ],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].created_at is None

    @pytest.mark.asyncio
    async def test_scan_no_status(self, cloudfront_scanner, mock_cloudfront_client):
        """Test scanning a distribution without Status field."""
        last_modified = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [
                    {
                        "Id": "E888888888888",
                        "LastModifiedTime": last_modified,
                    }
                ],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].state == "unknown"

    @pytest.mark.asyncio
    async def test_scan_region_is_always_global(self, cloudfront_scanner, mock_cloudfront_client):
        """Test that region is always set to 'global' regardless of input region."""
        last_modified = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [
                    {
                        "Id": "E123456789012",
                        "Status": "Deployed",
                        "LastModifiedTime": last_modified,
                    }
                ],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "eu-west-1")

        assert len(resources) == 1
        assert resources[0].region == "global"

    @pytest.mark.asyncio
    async def test_scan_all_resources_are_detected_resource(self, cloudfront_scanner, mock_cloudfront_client):
        """Test that all returned items are proper DetectedResource instances."""
        last_modified = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        mock_cloudfront_client.list_distributions.return_value = {
            "DistributionList": {
                "IsTruncated": False,
                "Items": [
                    {
                        "Id": "E111",
                        "Status": "Deployed",
                        "LastModifiedTime": last_modified,
                    },
                    {
                        "Id": "E222",
                        "Status": "InProgress",
                        "LastModifiedTime": last_modified,
                    },
                ],
            }
        }

        resources = await cloudfront_scanner.scan(mock_cloudfront_client, "us-east-1")

        for resource in resources:
            assert isinstance(resource, DetectedResource)
            assert resource.service == "cloudfront"
            assert resource.resource_type == "distribution"
            assert resource.region == "global"
