"""Tests for the RDS scanner."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.models.resource import DetectedResource
from backend.services.scanners.rds import RDSScanner


class TestRDSScannerAttributes:
    """Tests for RDSScanner class attributes."""

    def test_service_name_is_rds(self):
        """RDSScanner service_name is 'rds'."""
        scanner = RDSScanner()
        assert scanner.service_name == "rds"

    def test_is_not_global(self):
        """RDSScanner is a regional service (is_global=False)."""
        scanner = RDSScanner()
        assert scanner.is_global is False


class TestRDSScannerDBInstances:
    """Tests for scanning DB instances."""

    @pytest.mark.asyncio
    async def test_scan_single_db_instance(self):
        """Scan returns a DetectedResource for a single DB instance."""
        scanner = RDSScanner()
        client = MagicMock()
        create_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        client.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "my-database",
                    "DBInstanceStatus": "available",
                    "InstanceCreateTime": create_time,
                }
            ]
        }
        client.describe_db_clusters.return_value = {"DBClusters": []}

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "my-database"
        assert resources[0].resource_type == "db_instance"
        assert resources[0].service == "rds"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at == create_time.isoformat()
        assert resources[0].state == "available"

    @pytest.mark.asyncio
    async def test_scan_db_instance_without_create_time(self):
        """DB instance without InstanceCreateTime has created_at=None."""
        scanner = RDSScanner()
        client = MagicMock()

        client.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "no-time-db",
                    "DBInstanceStatus": "creating",
                }
            ]
        }
        client.describe_db_clusters.return_value = {"DBClusters": []}

        resources = await scanner.scan(client, "eu-west-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "no-time-db"
        assert resources[0].created_at is None
        assert resources[0].state == "creating"

    @pytest.mark.asyncio
    async def test_scan_db_instances_with_pagination(self):
        """Paginated DB instances are all returned."""
        scanner = RDSScanner()
        client = MagicMock()

        client.describe_db_instances.side_effect = [
            {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "db-1",
                        "DBInstanceStatus": "available",
                    }
                ],
                "Marker": "page2-marker",
            },
            {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "db-2",
                        "DBInstanceStatus": "stopped",
                    }
                ],
            },
        ]
        client.describe_db_clusters.return_value = {"DBClusters": []}

        resources = await scanner.scan(client, "us-west-2")

        db_instances = [r for r in resources if r.resource_type == "db_instance"]
        assert len(db_instances) == 2
        assert db_instances[0].resource_id == "db-1"
        assert db_instances[1].resource_id == "db-2"

        # Verify pagination was followed
        assert client.describe_db_instances.call_count == 2

    @pytest.mark.asyncio
    async def test_scan_no_db_instances(self):
        """Empty DB instances list returns no resources."""
        scanner = RDSScanner()
        client = MagicMock()

        client.describe_db_instances.return_value = {"DBInstances": []}
        client.describe_db_clusters.return_value = {"DBClusters": []}

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 0


class TestRDSScannerDBClusters:
    """Tests for scanning DB clusters."""

    @pytest.mark.asyncio
    async def test_scan_single_db_cluster(self):
        """Scan returns a DetectedResource for a single DB cluster."""
        scanner = RDSScanner()
        client = MagicMock()
        create_time = datetime(2024, 3, 20, 14, 0, 0, tzinfo=timezone.utc)

        client.describe_db_instances.return_value = {"DBInstances": []}
        client.describe_db_clusters.return_value = {
            "DBClusters": [
                {
                    "DBClusterIdentifier": "my-cluster",
                    "Status": "available",
                    "ClusterCreateTime": create_time,
                }
            ]
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert resources[0].resource_id == "my-cluster"
        assert resources[0].resource_type == "db_cluster"
        assert resources[0].service == "rds"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at == create_time.isoformat()
        assert resources[0].state == "available"

    @pytest.mark.asyncio
    async def test_scan_db_cluster_without_create_time(self):
        """DB cluster without ClusterCreateTime has created_at=None."""
        scanner = RDSScanner()
        client = MagicMock()

        client.describe_db_instances.return_value = {"DBInstances": []}
        client.describe_db_clusters.return_value = {
            "DBClusters": [
                {
                    "DBClusterIdentifier": "new-cluster",
                    "Status": "creating",
                }
            ]
        }

        resources = await scanner.scan(client, "ap-southeast-1")

        assert len(resources) == 1
        assert resources[0].created_at is None
        assert resources[0].state == "creating"

    @pytest.mark.asyncio
    async def test_scan_db_clusters_with_pagination(self):
        """Paginated DB clusters are all returned."""
        scanner = RDSScanner()
        client = MagicMock()

        client.describe_db_instances.return_value = {"DBInstances": []}
        client.describe_db_clusters.side_effect = [
            {
                "DBClusters": [
                    {
                        "DBClusterIdentifier": "cluster-1",
                        "Status": "available",
                    }
                ],
                "Marker": "next-page",
            },
            {
                "DBClusters": [
                    {
                        "DBClusterIdentifier": "cluster-2",
                        "Status": "available",
                    }
                ],
            },
        ]

        resources = await scanner.scan(client, "us-east-1")

        db_clusters = [r for r in resources if r.resource_type == "db_cluster"]
        assert len(db_clusters) == 2
        assert db_clusters[0].resource_id == "cluster-1"
        assert db_clusters[1].resource_id == "cluster-2"
        assert client.describe_db_clusters.call_count == 2


class TestRDSScannerCombined:
    """Tests for combined DB instances and clusters scanning."""

    @pytest.mark.asyncio
    async def test_scan_returns_both_instances_and_clusters(self):
        """Scan returns resources from both DB instances and clusters."""
        scanner = RDSScanner()
        client = MagicMock()
        create_time = datetime(2024, 2, 10, 8, 0, 0, tzinfo=timezone.utc)

        client.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "instance-1",
                    "DBInstanceStatus": "available",
                    "InstanceCreateTime": create_time,
                }
            ]
        }
        client.describe_db_clusters.return_value = {
            "DBClusters": [
                {
                    "DBClusterIdentifier": "cluster-1",
                    "Status": "available",
                    "ClusterCreateTime": create_time,
                }
            ]
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 2
        types = {r.resource_type for r in resources}
        assert types == {"db_instance", "db_cluster"}

    @pytest.mark.asyncio
    async def test_scan_uses_correct_region(self):
        """All resources have the region passed to scan."""
        scanner = RDSScanner()
        client = MagicMock()

        client.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "db-1",
                    "DBInstanceStatus": "available",
                }
            ]
        }
        client.describe_db_clusters.return_value = {
            "DBClusters": [
                {
                    "DBClusterIdentifier": "cluster-1",
                    "Status": "available",
                }
            ]
        }

        resources = await scanner.scan(client, "ap-northeast-1")

        for resource in resources:
            assert resource.region == "ap-northeast-1"
            assert resource.service == "rds"
