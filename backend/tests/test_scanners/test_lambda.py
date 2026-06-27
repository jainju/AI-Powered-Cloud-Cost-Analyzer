"""Tests for the Lambda scanner."""

import pytest
from unittest.mock import MagicMock

from backend.models.resource import DetectedResource
from backend.services.scanners.lambda_scanner import LambdaScanner


class TestLambdaScanner:
    """Tests for LambdaScanner class."""

    def test_service_name(self):
        """LambdaScanner has correct service_name."""
        scanner = LambdaScanner()
        assert scanner.service_name == "lambda"

    def test_is_not_global(self):
        """LambdaScanner is a regional service."""
        scanner = LambdaScanner()
        assert scanner.is_global is False

    @pytest.mark.asyncio
    async def test_scan_single_function(self):
        """Scan returns a single Lambda function correctly mapped."""
        scanner = LambdaScanner()
        client = MagicMock()
        client.list_functions.return_value = {
            "Functions": [
                {
                    "FunctionName": "my-function",
                    "State": "Active",
                    "LastModified": "2024-01-15T10:30:00.000+0000",
                }
            ]
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert isinstance(resources[0], DetectedResource)
        assert resources[0].resource_id == "my-function"
        assert resources[0].resource_type == "function"
        assert resources[0].service == "lambda"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at == "2024-01-15T10:30:00.000+0000"
        assert resources[0].state == "Active"

    @pytest.mark.asyncio
    async def test_scan_no_functions(self):
        """Scan returns empty list when no functions exist."""
        scanner = LambdaScanner()
        client = MagicMock()
        client.list_functions.return_value = {"Functions": []}

        resources = await scanner.scan(client, "us-west-2")

        assert resources == []
        client.list_functions.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_multiple_functions(self):
        """Scan returns multiple functions correctly."""
        scanner = LambdaScanner()
        client = MagicMock()
        client.list_functions.return_value = {
            "Functions": [
                {
                    "FunctionName": "func-a",
                    "State": "Active",
                    "LastModified": "2024-01-10T08:00:00.000+0000",
                },
                {
                    "FunctionName": "func-b",
                    "State": "Inactive",
                    "LastModified": "2024-02-20T14:00:00.000+0000",
                },
            ]
        }

        resources = await scanner.scan(client, "eu-west-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "func-a"
        assert resources[0].state == "Active"
        assert resources[1].resource_id == "func-b"
        assert resources[1].state == "Inactive"

    @pytest.mark.asyncio
    async def test_scan_handles_pagination(self):
        """Scan retrieves all pages of results using Marker/NextMarker."""
        scanner = LambdaScanner()
        client = MagicMock()

        # First page with NextMarker
        client.list_functions.side_effect = [
            {
                "Functions": [
                    {
                        "FunctionName": "func-page1",
                        "State": "Active",
                        "LastModified": "2024-01-01T00:00:00.000+0000",
                    }
                ],
                "NextMarker": "marker-abc",
            },
            # Second page without NextMarker (last page)
            {
                "Functions": [
                    {
                        "FunctionName": "func-page2",
                        "State": "Active",
                        "LastModified": "2024-02-01T00:00:00.000+0000",
                    }
                ],
            },
        ]

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "func-page1"
        assert resources[1].resource_id == "func-page2"

        # Verify pagination was handled
        assert client.list_functions.call_count == 2
        # First call with no marker
        client.list_functions.assert_any_call()
        # Second call with marker
        client.list_functions.assert_any_call(Marker="marker-abc")

    @pytest.mark.asyncio
    async def test_scan_handles_three_pages(self):
        """Scan correctly handles three pages of results."""
        scanner = LambdaScanner()
        client = MagicMock()

        client.list_functions.side_effect = [
            {
                "Functions": [{"FunctionName": "func-1", "State": "Active", "LastModified": "2024-01-01T00:00:00.000+0000"}],
                "NextMarker": "marker-1",
            },
            {
                "Functions": [{"FunctionName": "func-2", "State": "Active", "LastModified": "2024-01-02T00:00:00.000+0000"}],
                "NextMarker": "marker-2",
            },
            {
                "Functions": [{"FunctionName": "func-3", "State": "Active", "LastModified": "2024-01-03T00:00:00.000+0000"}],
            },
        ]

        resources = await scanner.scan(client, "ap-southeast-1")

        assert len(resources) == 3
        assert [r.resource_id for r in resources] == ["func-1", "func-2", "func-3"]
        assert client.list_functions.call_count == 3

    @pytest.mark.asyncio
    async def test_scan_function_without_state_defaults_to_active(self):
        """Functions without a State field default to 'active'."""
        scanner = LambdaScanner()
        client = MagicMock()
        client.list_functions.return_value = {
            "Functions": [
                {
                    "FunctionName": "no-state-func",
                    "LastModified": "2024-03-01T12:00:00.000+0000",
                }
            ]
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].state == "active"

    @pytest.mark.asyncio
    async def test_scan_function_without_last_modified(self):
        """Functions without LastModified have created_at as None."""
        scanner = LambdaScanner()
        client = MagicMock()
        client.list_functions.return_value = {
            "Functions": [
                {
                    "FunctionName": "no-date-func",
                    "State": "Active",
                }
            ]
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].created_at is None

    @pytest.mark.asyncio
    async def test_scan_uses_correct_region(self):
        """Scan passes the correct region to each resource."""
        scanner = LambdaScanner()
        client = MagicMock()
        client.list_functions.return_value = {
            "Functions": [
                {
                    "FunctionName": "regional-func",
                    "State": "Active",
                    "LastModified": "2024-01-01T00:00:00.000+0000",
                }
            ]
        }

        resources = await scanner.scan(client, "ap-northeast-1")

        assert resources[0].region == "ap-northeast-1"
