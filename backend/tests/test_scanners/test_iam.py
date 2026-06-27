"""Tests for the IAM scanner."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.models.resource import DetectedResource
from backend.services.scanners.iam import IAMScanner


class TestIAMScannerAttributes:
    """Tests for IAMScanner class attributes."""

    def test_service_name_is_iam(self):
        """The service_name attribute is 'iam'."""
        scanner = IAMScanner()
        assert scanner.service_name == "iam"

    def test_is_global_is_true(self):
        """IAM is a global service."""
        scanner = IAMScanner()
        assert scanner.is_global is True


class TestIAMScannerScanUsers:
    """Tests for IAM user scanning."""

    @pytest.mark.asyncio
    async def test_scan_returns_users(self):
        """Users returned by list_users are mapped to DetectedResource."""
        client = MagicMock()
        create_date = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        client.list_users.return_value = {
            "Users": [
                {
                    "UserName": "admin-user",
                    "CreateDate": create_date,
                }
            ],
            "IsTruncated": False,
        }
        client.list_roles.return_value = {
            "Roles": [],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        assert len(results) == 1
        user = results[0]
        assert user.resource_id == "admin-user"
        assert user.resource_type == "user"
        assert user.service == "iam"
        assert user.region == "global"
        assert user.created_at == create_date.isoformat()
        assert user.state == "active"

    @pytest.mark.asyncio
    async def test_scan_users_pagination(self):
        """Users are retrieved across multiple pages using Marker/IsTruncated."""
        client = MagicMock()
        client.list_users.side_effect = [
            {
                "Users": [
                    {"UserName": "user-1", "CreateDate": datetime(2023, 1, 1, tzinfo=timezone.utc)},
                    {"UserName": "user-2", "CreateDate": datetime(2023, 2, 1, tzinfo=timezone.utc)},
                ],
                "IsTruncated": True,
                "Marker": "marker-page-2",
            },
            {
                "Users": [
                    {"UserName": "user-3", "CreateDate": datetime(2023, 3, 1, tzinfo=timezone.utc)},
                ],
                "IsTruncated": False,
            },
        ]
        client.list_roles.return_value = {
            "Roles": [],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        user_names = [r.resource_id for r in results if r.resource_type == "user"]
        assert user_names == ["user-1", "user-2", "user-3"]

        # Verify pagination marker was passed
        calls = client.list_users.call_args_list
        assert len(calls) == 2
        assert calls[0] == ((), {})
        assert calls[1] == ((), {"Marker": "marker-page-2"})


class TestIAMScannerScanRoles:
    """Tests for IAM role scanning."""

    @pytest.mark.asyncio
    async def test_scan_returns_roles(self):
        """Roles returned by list_roles are mapped to DetectedResource."""
        client = MagicMock()
        create_date = datetime(2022, 12, 1, 8, 0, 0, tzinfo=timezone.utc)
        client.list_users.return_value = {
            "Users": [],
            "IsTruncated": False,
        }
        client.list_roles.return_value = {
            "Roles": [
                {
                    "RoleName": "lambda-execution-role",
                    "CreateDate": create_date,
                }
            ],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        assert len(results) == 1
        role = results[0]
        assert role.resource_id == "lambda-execution-role"
        assert role.resource_type == "role"
        assert role.service == "iam"
        assert role.region == "global"
        assert role.created_at == create_date.isoformat()
        assert role.state == "active"

    @pytest.mark.asyncio
    async def test_scan_roles_pagination(self):
        """Roles are retrieved across multiple pages using Marker/IsTruncated."""
        client = MagicMock()
        client.list_users.return_value = {
            "Users": [],
            "IsTruncated": False,
        }
        client.list_roles.side_effect = [
            {
                "Roles": [
                    {"RoleName": "role-1", "CreateDate": datetime(2023, 1, 1, tzinfo=timezone.utc)},
                ],
                "IsTruncated": True,
                "Marker": "role-marker-2",
            },
            {
                "Roles": [
                    {"RoleName": "role-2", "CreateDate": datetime(2023, 2, 1, tzinfo=timezone.utc)},
                    {"RoleName": "role-3", "CreateDate": datetime(2023, 3, 1, tzinfo=timezone.utc)},
                ],
                "IsTruncated": False,
            },
        ]

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        role_names = [r.resource_id for r in results if r.resource_type == "role"]
        assert role_names == ["role-1", "role-2", "role-3"]

        # Verify pagination marker was passed
        calls = client.list_roles.call_args_list
        assert len(calls) == 2
        assert calls[0] == ((), {})
        assert calls[1] == ((), {"Marker": "role-marker-2"})


class TestIAMScannerCombined:
    """Tests for combined user and role scanning."""

    @pytest.mark.asyncio
    async def test_scan_returns_both_users_and_roles(self):
        """Scan returns resources from both users and roles."""
        client = MagicMock()
        client.list_users.return_value = {
            "Users": [
                {"UserName": "dev-user", "CreateDate": datetime(2023, 5, 1, tzinfo=timezone.utc)},
            ],
            "IsTruncated": False,
        }
        client.list_roles.return_value = {
            "Roles": [
                {"RoleName": "admin-role", "CreateDate": datetime(2023, 6, 1, tzinfo=timezone.utc)},
            ],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        assert len(results) == 2
        types = {r.resource_type for r in results}
        assert types == {"user", "role"}

    @pytest.mark.asyncio
    async def test_scan_empty_account(self):
        """Scan returns empty list when no users or roles exist."""
        client = MagicMock()
        client.list_users.return_value = {
            "Users": [],
            "IsTruncated": False,
        }
        client.list_roles.return_value = {
            "Roles": [],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        assert results == []

    @pytest.mark.asyncio
    async def test_scan_user_without_create_date(self):
        """Users without CreateDate have created_at set to None."""
        client = MagicMock()
        client.list_users.return_value = {
            "Users": [
                {"UserName": "legacy-user"},
            ],
            "IsTruncated": False,
        }
        client.list_roles.return_value = {
            "Roles": [],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        assert len(results) == 1
        assert results[0].created_at is None

    @pytest.mark.asyncio
    async def test_all_resources_are_detected_resource_instances(self):
        """All returned items are DetectedResource instances."""
        client = MagicMock()
        client.list_users.return_value = {
            "Users": [
                {"UserName": "user-a", "CreateDate": datetime(2023, 1, 1, tzinfo=timezone.utc)},
            ],
            "IsTruncated": False,
        }
        client.list_roles.return_value = {
            "Roles": [
                {"RoleName": "role-a", "CreateDate": datetime(2023, 2, 1, tzinfo=timezone.utc)},
            ],
            "IsTruncated": False,
        }

        scanner = IAMScanner()
        results = await scanner.scan(client, "us-east-1")

        for resource in results:
            assert isinstance(resource, DetectedResource)
