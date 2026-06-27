"""Tests for the base scanner interface."""

import pytest
from typing import List
from unittest.mock import MagicMock

from backend.models.resource import DetectedResource
from backend.services.scanners.base import BaseScanner


class ConcreteRegionalScanner(BaseScanner):
    """A concrete implementation for testing the abstract base class."""

    service_name = "ec2"
    is_global = False

    async def scan(self, client, region: str) -> List[DetectedResource]:
        return [
            DetectedResource(
                resource_id="i-12345",
                resource_type="instance",
                service="ec2",
                region=region,
                state="running",
            )
        ]


class ConcreteGlobalScanner(BaseScanner):
    """A concrete global scanner implementation for testing."""

    service_name = "s3"
    is_global = True

    async def scan(self, client, region: str) -> List[DetectedResource]:
        return [
            DetectedResource(
                resource_id="my-bucket",
                resource_type="bucket",
                service="s3",
                region="global",
                state="active",
            )
        ]


class TestBaseScannerInterface:
    """Tests for the BaseScanner abstract class."""

    def test_cannot_instantiate_abstract_class(self):
        """BaseScanner cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseScanner()

    def test_regional_scanner_service_name(self):
        """Regional scanner has correct service_name attribute."""
        scanner = ConcreteRegionalScanner()
        assert scanner.service_name == "ec2"

    def test_regional_scanner_is_not_global(self):
        """Regional scanner has is_global set to False."""
        scanner = ConcreteRegionalScanner()
        assert scanner.is_global is False

    def test_global_scanner_is_global(self):
        """Global scanner has is_global set to True."""
        scanner = ConcreteGlobalScanner()
        assert scanner.is_global is True

    def test_global_scanner_service_name(self):
        """Global scanner has correct service_name attribute."""
        scanner = ConcreteGlobalScanner()
        assert scanner.service_name == "s3"

    @pytest.mark.asyncio
    async def test_regional_scanner_scan_returns_resources(self):
        """Regional scanner scan method returns list of DetectedResource."""
        scanner = ConcreteRegionalScanner()
        client = MagicMock()
        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert isinstance(resources[0], DetectedResource)
        assert resources[0].resource_id == "i-12345"
        assert resources[0].region == "us-east-1"

    @pytest.mark.asyncio
    async def test_global_scanner_scan_returns_resources(self):
        """Global scanner scan method returns list of DetectedResource."""
        scanner = ConcreteGlobalScanner()
        client = MagicMock()
        resources = await scanner.scan(client, "us-east-1")

        assert len(resources) == 1
        assert isinstance(resources[0], DetectedResource)
        assert resources[0].resource_id == "my-bucket"
        assert resources[0].service == "s3"

    def test_default_is_global_is_false(self):
        """The default value of is_global is False."""

        class MinimalScanner(BaseScanner):
            service_name = "test"

            async def scan(self, client, region: str) -> List[DetectedResource]:
                return []

        scanner = MinimalScanner()
        assert scanner.is_global is False

    def test_subclass_must_implement_scan(self):
        """A subclass that doesn't implement scan cannot be instantiated."""

        class IncompleteScanner(BaseScanner):
            service_name = "incomplete"

        with pytest.raises(TypeError):
            IncompleteScanner()
