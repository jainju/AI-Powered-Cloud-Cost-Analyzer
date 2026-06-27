"""Unit tests for the EC2 scanner."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.models.resource import DetectedResource
from backend.services.scanners.ec2 import EC2Scanner


@pytest.fixture
def ec2_scanner():
    """Create an EC2Scanner instance."""
    return EC2Scanner()


@pytest.fixture
def mock_ec2_client():
    """Create a mock EC2 client with paginator support."""
    client = MagicMock()
    return client


class TestEC2ScannerAttributes:
    """Tests for EC2Scanner class attributes."""

    def test_service_name(self, ec2_scanner):
        assert ec2_scanner.service_name == "ec2"

    def test_is_not_global(self, ec2_scanner):
        assert ec2_scanner.is_global is False


class TestScanInstances:
    """Tests for EC2 instance scanning."""

    def test_scan_instances_single_page(self, ec2_scanner, mock_ec2_client):
        """Test scanning instances with a single page of results."""
        launch_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-1234567890abcdef0",
                                "State": {"Name": "running"},
                                "LaunchTime": launch_time,
                            }
                        ]
                    }
                ]
            }
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_instances(mock_ec2_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "i-1234567890abcdef0"
        assert resources[0].resource_type == "instance"
        assert resources[0].service == "ec2"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at == launch_time.isoformat()
        assert resources[0].state == "running"

    def test_scan_instances_multiple_pages(self, ec2_scanner, mock_ec2_client):
        """Test scanning instances across multiple paginated pages."""
        launch_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-111",
                                "State": {"Name": "running"},
                                "LaunchTime": launch_time,
                            }
                        ]
                    }
                ]
            },
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-222",
                                "State": {"Name": "stopped"},
                                "LaunchTime": launch_time,
                            }
                        ]
                    }
                ]
            },
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_instances(mock_ec2_client, "us-west-2")

        assert len(resources) == 2
        assert resources[0].resource_id == "i-111"
        assert resources[0].state == "running"
        assert resources[1].resource_id == "i-222"
        assert resources[1].state == "stopped"

    def test_scan_instances_empty(self, ec2_scanner, mock_ec2_client):
        """Test scanning when no instances exist."""
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Reservations": []}]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_instances(mock_ec2_client, "us-east-1")

        assert resources == []

    def test_scan_instances_no_launch_time(self, ec2_scanner, mock_ec2_client):
        """Test scanning instances without a launch time."""
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-nolt",
                                "State": {"Name": "pending"},
                            }
                        ]
                    }
                ]
            }
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_instances(mock_ec2_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].created_at is None

    def test_scan_instances_multiple_reservations(self, ec2_scanner, mock_ec2_client):
        """Test scanning instances across multiple reservations."""
        launch_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-aaa",
                                "State": {"Name": "running"},
                                "LaunchTime": launch_time,
                            }
                        ]
                    },
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-bbb",
                                "State": {"Name": "running"},
                                "LaunchTime": launch_time,
                            }
                        ]
                    },
                ]
            }
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_instances(mock_ec2_client, "us-east-1")

        assert len(resources) == 2


class TestScanVolumes:
    """Tests for EBS volume scanning."""

    def test_scan_volumes_single_page(self, ec2_scanner, mock_ec2_client):
        """Test scanning volumes with a single page."""
        create_time = datetime(2024, 2, 10, 8, 0, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Volumes": [
                    {
                        "VolumeId": "vol-0123456789abcdef0",
                        "State": "available",
                        "CreateTime": create_time,
                    }
                ]
            }
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_volumes(mock_ec2_client, "eu-west-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "vol-0123456789abcdef0"
        assert resources[0].resource_type == "volume"
        assert resources[0].service == "ec2"
        assert resources[0].region == "eu-west-1"
        assert resources[0].created_at == create_time.isoformat()
        assert resources[0].state == "available"

    def test_scan_volumes_multiple_pages(self, ec2_scanner, mock_ec2_client):
        """Test scanning volumes across multiple pages."""
        create_time = datetime(2024, 2, 10, 8, 0, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Volumes": [
                    {"VolumeId": "vol-aaa", "State": "in-use", "CreateTime": create_time}
                ]
            },
            {
                "Volumes": [
                    {"VolumeId": "vol-bbb", "State": "available", "CreateTime": create_time}
                ]
            },
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_volumes(mock_ec2_client, "us-east-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "vol-aaa"
        assert resources[1].resource_id == "vol-bbb"

    def test_scan_volumes_empty(self, ec2_scanner, mock_ec2_client):
        """Test scanning when no volumes exist."""
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Volumes": []}]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_volumes(mock_ec2_client, "us-east-1")

        assert resources == []


class TestScanSnapshots:
    """Tests for EBS snapshot scanning."""

    def test_scan_snapshots_single_page(self, ec2_scanner, mock_ec2_client):
        """Test scanning snapshots with a single page."""
        start_time = datetime(2024, 3, 5, 14, 0, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Snapshots": [
                    {
                        "SnapshotId": "snap-0123456789abcdef0",
                        "State": "completed",
                        "StartTime": start_time,
                    }
                ]
            }
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_snapshots(mock_ec2_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "snap-0123456789abcdef0"
        assert resources[0].resource_type == "snapshot"
        assert resources[0].service == "ec2"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at == start_time.isoformat()
        assert resources[0].state == "completed"

    def test_scan_snapshots_uses_owner_filter(self, ec2_scanner, mock_ec2_client):
        """Test that snapshots are filtered to self-owned only."""
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Snapshots": []}]
        mock_ec2_client.get_paginator.return_value = paginator

        ec2_scanner._scan_snapshots(mock_ec2_client, "us-east-1")

        paginator.paginate.assert_called_once_with(OwnerIds=["self"])

    def test_scan_snapshots_multiple_pages(self, ec2_scanner, mock_ec2_client):
        """Test scanning snapshots across multiple pages."""
        start_time = datetime(2024, 3, 5, 14, 0, 0, tzinfo=timezone.utc)

        paginator = MagicMock()
        paginator.paginate.return_value = [
            {
                "Snapshots": [
                    {"SnapshotId": "snap-aaa", "State": "completed", "StartTime": start_time}
                ]
            },
            {
                "Snapshots": [
                    {"SnapshotId": "snap-bbb", "State": "pending", "StartTime": start_time}
                ]
            },
        ]
        mock_ec2_client.get_paginator.return_value = paginator

        resources = ec2_scanner._scan_snapshots(mock_ec2_client, "us-east-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "snap-aaa"
        assert resources[1].resource_id == "snap-bbb"


class TestScanElasticIPs:
    """Tests for elastic IP scanning."""

    def test_scan_elastic_ips_associated(self, ec2_scanner, mock_ec2_client):
        """Test scanning an elastic IP that is associated."""
        mock_ec2_client.describe_addresses.return_value = {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-12345",
                    "PublicIp": "54.123.45.67",
                    "AssociationId": "eipassoc-67890",
                }
            ]
        }

        resources = ec2_scanner._scan_elastic_ips(mock_ec2_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "eipalloc-12345"
        assert resources[0].resource_type == "elastic_ip"
        assert resources[0].service == "ec2"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at is None
        assert resources[0].state == "associated"

    def test_scan_elastic_ips_disassociated(self, ec2_scanner, mock_ec2_client):
        """Test scanning an elastic IP that is not associated."""
        mock_ec2_client.describe_addresses.return_value = {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-99999",
                    "PublicIp": "52.10.20.30",
                }
            ]
        }

        resources = ec2_scanner._scan_elastic_ips(mock_ec2_client, "eu-west-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "eipalloc-99999"
        assert resources[0].state == "disassociated"

    def test_scan_elastic_ips_empty(self, ec2_scanner, mock_ec2_client):
        """Test scanning when no elastic IPs exist."""
        mock_ec2_client.describe_addresses.return_value = {"Addresses": []}

        resources = ec2_scanner._scan_elastic_ips(mock_ec2_client, "us-east-1")

        assert resources == []

    def test_scan_elastic_ips_fallback_to_public_ip(self, ec2_scanner, mock_ec2_client):
        """Test that PublicIp is used as resource_id when AllocationId is absent."""
        mock_ec2_client.describe_addresses.return_value = {
            "Addresses": [
                {
                    "PublicIp": "203.0.113.25",
                }
            ]
        }

        resources = ec2_scanner._scan_elastic_ips(mock_ec2_client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "203.0.113.25"


class TestScanIntegration:
    """Integration tests for the full scan method."""

    @pytest.mark.asyncio
    async def test_scan_combines_all_resource_types(self, ec2_scanner, mock_ec2_client):
        """Test that scan() returns resources from all EC2 resource types."""
        launch_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        create_time = datetime(2024, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
        start_time = datetime(2024, 3, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Set up paginator for instances
        instance_paginator = MagicMock()
        instance_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-001",
                                "State": {"Name": "running"},
                                "LaunchTime": launch_time,
                            }
                        ]
                    }
                ]
            }
        ]

        # Set up paginator for volumes
        volume_paginator = MagicMock()
        volume_paginator.paginate.return_value = [
            {
                "Volumes": [
                    {"VolumeId": "vol-001", "State": "in-use", "CreateTime": create_time}
                ]
            }
        ]

        # Set up paginator for snapshots
        snapshot_paginator = MagicMock()
        snapshot_paginator.paginate.return_value = [
            {
                "Snapshots": [
                    {"SnapshotId": "snap-001", "State": "completed", "StartTime": start_time}
                ]
            }
        ]

        # Route get_paginator calls to the correct paginator
        def get_paginator_side_effect(operation):
            if operation == "describe_instances":
                return instance_paginator
            elif operation == "describe_volumes":
                return volume_paginator
            elif operation == "describe_snapshots":
                return snapshot_paginator
            return MagicMock()

        mock_ec2_client.get_paginator.side_effect = get_paginator_side_effect

        # Set up elastic IPs response
        mock_ec2_client.describe_addresses.return_value = {
            "Addresses": [
                {
                    "AllocationId": "eipalloc-001",
                    "PublicIp": "1.2.3.4",
                    "AssociationId": "eipassoc-001",
                }
            ]
        }

        resources = await ec2_scanner.scan(mock_ec2_client, "us-east-1")

        assert len(resources) == 4

        resource_types = {r.resource_type for r in resources}
        assert resource_types == {"instance", "volume", "snapshot", "elastic_ip"}

        # All should have service=ec2 and region=us-east-1
        for r in resources:
            assert r.service == "ec2"
            assert r.region == "us-east-1"
            assert isinstance(r, DetectedResource)

    @pytest.mark.asyncio
    async def test_scan_empty_account(self, ec2_scanner, mock_ec2_client):
        """Test scan on an account with no EC2 resources."""
        empty_paginator = MagicMock()
        empty_paginator.paginate.return_value = [
            {"Reservations": [], "Volumes": [], "Snapshots": []}
        ]
        mock_ec2_client.get_paginator.return_value = empty_paginator
        mock_ec2_client.describe_addresses.return_value = {"Addresses": []}

        resources = await ec2_scanner.scan(mock_ec2_client, "us-east-1")

        assert resources == []
