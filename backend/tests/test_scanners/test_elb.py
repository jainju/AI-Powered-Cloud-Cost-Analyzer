"""Tests for the ELB scanner."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.models.resource import DetectedResource
from backend.services.scanners.elb import ELBScanner


class TestELBScannerAttributes:
    """Tests for ELBScanner class attributes."""

    def test_service_name_is_elb(self):
        """ELBScanner service_name is 'elb'."""
        scanner = ELBScanner()
        assert scanner.service_name == "elb"

    def test_is_not_global(self):
        """ELBScanner is a regional scanner."""
        scanner = ELBScanner()
        assert scanner.is_global is False


class TestELBScannerScan:
    """Tests for ELBScanner.scan method."""

    @pytest.mark.asyncio
    async def test_scan_returns_empty_list_when_no_load_balancers(self):
        """Returns empty list when no load balancers exist."""
        scanner = ELBScanner()
        client = MagicMock()
        client.describe_load_balancers.return_value = {
            "LoadBalancers": []
        }

        resources = await scanner.scan(client, "us-east-1")

        assert resources == []
        client.describe_load_balancers.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_scan_returns_detected_resources(self):
        """Returns DetectedResource objects for each load balancer."""
        scanner = ELBScanner()
        client = MagicMock()
        created_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        client.describe_load_balancers.return_value = {
            "LoadBalancers": [
                {
                    "LoadBalancerName": "my-alb",
                    "LoadBalancerArn": "arn:aws:elasticloadbalancing:us-east-1:123456:loadbalancer/app/my-alb/abc123",
                    "Type": "application",
                    "CreatedTime": created_time,
                    "State": {"Code": "active"},
                }
            ]
        }

        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert isinstance(resources[0], DetectedResource)
        assert resources[0].resource_id == "my-alb"
        assert resources[0].resource_type == "load_balancer"
        assert resources[0].service == "elb"
        assert resources[0].region == "us-east-1"
        assert resources[0].created_at == created_time.isoformat()
        assert resources[0].state == "active"

    @pytest.mark.asyncio
    async def test_scan_handles_pagination(self):
        """Follows NextMarker to retrieve all pages of results."""
        scanner = ELBScanner()
        client = MagicMock()
        created_time = datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

        # First page returns one LB and a NextMarker
        client.describe_load_balancers.side_effect = [
            {
                "LoadBalancers": [
                    {
                        "LoadBalancerName": "lb-page-1",
                        "CreatedTime": created_time,
                        "State": {"Code": "active"},
                    }
                ],
                "NextMarker": "marker-abc",
            },
            {
                "LoadBalancers": [
                    {
                        "LoadBalancerName": "lb-page-2",
                        "CreatedTime": created_time,
                        "State": {"Code": "provisioning"},
                    }
                ],
            },
        ]

        resources = await scanner.scan(client, "eu-west-1")

        assert len(resources) == 2
        assert resources[0].resource_id == "lb-page-1"
        assert resources[0].state == "active"
        assert resources[1].resource_id == "lb-page-2"
        assert resources[1].state == "provisioning"
        assert resources[1].region == "eu-west-1"

        # Verify pagination calls
        assert client.describe_load_balancers.call_count == 2
        client.describe_load_balancers.assert_any_call()
        client.describe_load_balancers.assert_any_call(Marker="marker-abc")

    @pytest.mark.asyncio
    async def test_scan_handles_missing_created_time(self):
        """Sets created_at to None when CreatedTime is not present."""
        scanner = ELBScanner()
        client = MagicMock()

        client.describe_load_balancers.return_value = {
            "LoadBalancers": [
                {
                    "LoadBalancerName": "lb-no-time",
                    "State": {"Code": "active"},
                }
            ]
        }

        resources = await scanner.scan(client, "us-west-2")

        assert len(resources) == 1
        assert resources[0].created_at is None

    @pytest.mark.asyncio
    async def test_scan_handles_missing_state(self):
        """Defaults state to 'unknown' when State is not present."""
        scanner = ELBScanner()
        client = MagicMock()

        client.describe_load_balancers.return_value = {
            "LoadBalancers": [
                {
                    "LoadBalancerName": "lb-no-state",
                    "CreatedTime": datetime(2024, 3, 1, tzinfo=timezone.utc),
                }
            ]
        }

        resources = await scanner.scan(client, "us-west-2")

        assert len(resources) == 1
        assert resources[0].state == "unknown"

    @pytest.mark.asyncio
    async def test_scan_multiple_load_balancers_single_page(self):
        """Handles multiple load balancers in a single response page."""
        scanner = ELBScanner()
        client = MagicMock()
        created_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

        client.describe_load_balancers.return_value = {
            "LoadBalancers": [
                {
                    "LoadBalancerName": "alb-1",
                    "CreatedTime": created_time,
                    "State": {"Code": "active"},
                },
                {
                    "LoadBalancerName": "nlb-1",
                    "CreatedTime": created_time,
                    "State": {"Code": "active"},
                },
                {
                    "LoadBalancerName": "gwlb-1",
                    "CreatedTime": created_time,
                    "State": {"Code": "provisioning"},
                },
            ]
        }

        resources = await scanner.scan(client, "ap-southeast-1")

        assert len(resources) == 3
        assert resources[0].resource_id == "alb-1"
        assert resources[1].resource_id == "nlb-1"
        assert resources[2].resource_id == "gwlb-1"
        # All should have consistent service and type
        for r in resources:
            assert r.service == "elb"
            assert r.resource_type == "load_balancer"
            assert r.region == "ap-southeast-1"
