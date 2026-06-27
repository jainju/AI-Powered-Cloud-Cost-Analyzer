"""Unit tests for the AWS Client Factory (task 3.1)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.config.settings import Settings
from backend.services.aws_client import AuthenticationError, AWSClientFactory


def _make_settings(**overrides):
    """Create a Settings instance with valid defaults for testing."""
    defaults = {
        "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_default_region": "us-east-1",
        "aws_regions": ["us-east-1", "eu-west-1"],
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestAWSClientFactoryInit:
    """Test AWSClientFactory initialization."""

    def test_successful_init_with_valid_credentials(self):
        """Factory initializes successfully with valid credential settings."""
        settings = _make_settings()
        factory = AWSClientFactory(settings)
        assert factory is not None

    def test_successful_init_with_session_token(self):
        """Factory initializes successfully with optional session token."""
        settings = _make_settings(aws_session_token="FwoGZXIvYXdzEBY")
        factory = AWSClientFactory(settings)
        assert factory is not None

    def test_raises_error_when_access_key_empty(self):
        """Factory raises AuthenticationError when access key is empty string."""
        settings = _make_settings(aws_access_key_id="")
        with pytest.raises(AuthenticationError) as exc_info:
            AWSClientFactory(settings)
        assert "AWS_ACCESS_KEY_ID" in str(exc_info.value)

    def test_raises_error_when_secret_key_empty(self):
        """Factory raises AuthenticationError when secret key is empty string."""
        settings = _make_settings(aws_secret_access_key="")
        with pytest.raises(AuthenticationError) as exc_info:
            AWSClientFactory(settings)
        assert "AWS_SECRET_ACCESS_KEY" in str(exc_info.value)

    def test_raises_error_with_both_credentials_missing(self):
        """Factory raises AuthenticationError listing both missing variables."""
        settings = _make_settings(
            aws_access_key_id="", aws_secret_access_key=""
        )
        with pytest.raises(AuthenticationError) as exc_info:
            AWSClientFactory(settings)
        error_msg = str(exc_info.value)
        assert "AWS_ACCESS_KEY_ID" in error_msg
        assert "AWS_SECRET_ACCESS_KEY" in error_msg


class TestValidateCredentials:
    """Test credential validation via STS."""

    @patch("boto3.Session")
    def test_validate_credentials_success(self, mock_session_class):
        """validate_credentials succeeds when STS returns caller identity."""
        mock_session = MagicMock()
        mock_sts_client = MagicMock()
        mock_sts_client.get_caller_identity.return_value = {
            "UserId": "AIDACKCEVSQ6C2EXAMPLE",
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/testuser",
        }
        mock_session.client.return_value = mock_sts_client
        mock_session_class.return_value = mock_session

        settings = _make_settings()
        factory = AWSClientFactory(settings)
        # Should not raise
        factory.validate_credentials()
        mock_session.client.assert_called_with("sts")
        mock_sts_client.get_caller_identity.assert_called_once()

    @patch("boto3.Session")
    def test_validate_credentials_invalid_credentials(self, mock_session_class):
        """validate_credentials raises AuthenticationError with AWS failure reason."""
        from botocore.exceptions import ClientError

        mock_session = MagicMock()
        mock_sts_client = MagicMock()
        mock_sts_client.get_caller_identity.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InvalidClientTokenId",
                    "Message": "The security token included in the request is invalid.",
                }
            },
            "GetCallerIdentity",
        )
        mock_session.client.return_value = mock_sts_client
        mock_session_class.return_value = mock_session

        settings = _make_settings()
        factory = AWSClientFactory(settings)
        with pytest.raises(AuthenticationError) as exc_info:
            factory.validate_credentials()
        error_msg = str(exc_info.value)
        assert "AWS authentication failed" in error_msg
        assert "security token included in the request is invalid" in error_msg

    @patch("boto3.Session")
    def test_validate_credentials_expired_token(self, mock_session_class):
        """validate_credentials raises AuthenticationError for expired tokens."""
        from botocore.exceptions import ClientError

        mock_session = MagicMock()
        mock_sts_client = MagicMock()
        mock_sts_client.get_caller_identity.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ExpiredTokenException",
                    "Message": "The security token included in the request is expired",
                }
            },
            "GetCallerIdentity",
        )
        mock_session.client.return_value = mock_sts_client
        mock_session_class.return_value = mock_session

        settings = _make_settings()
        factory = AWSClientFactory(settings)
        with pytest.raises(AuthenticationError) as exc_info:
            factory.validate_credentials()
        assert "AWS authentication failed" in str(exc_info.value)
        assert "expired" in str(exc_info.value)

    @patch("boto3.Session")
    def test_validate_credentials_no_credentials_error(self, mock_session_class):
        """validate_credentials raises AuthenticationError for NoCredentialsError."""
        from botocore.exceptions import NoCredentialsError

        mock_session = MagicMock()
        mock_sts_client = MagicMock()
        mock_sts_client.get_caller_identity.side_effect = NoCredentialsError()
        mock_session.client.return_value = mock_sts_client
        mock_session_class.return_value = mock_session

        settings = _make_settings()
        factory = AWSClientFactory(settings)
        with pytest.raises(AuthenticationError) as exc_info:
            factory.validate_credentials()
        assert "AWS authentication failed" in str(exc_info.value)
        assert "No credentials" in str(exc_info.value)


class TestCreateClient:
    """Test boto3 client creation."""

    @patch("boto3.Session")
    def test_create_client_returns_service_client(self, mock_session_class):
        """create_client returns a boto3 client for the specified service/region."""
        mock_session = MagicMock()
        mock_ec2_client = MagicMock()
        mock_session.client.return_value = mock_ec2_client
        mock_session_class.return_value = mock_session

        settings = _make_settings()
        factory = AWSClientFactory(settings)
        client = factory.create_client("ec2", "us-west-2")

        mock_session.client.assert_called_with("ec2", region_name="us-west-2")
        assert client == mock_ec2_client

    @patch("boto3.Session")
    def test_create_client_different_services(self, mock_session_class):
        """create_client works for various AWS service names."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        settings = _make_settings()
        factory = AWSClientFactory(settings)

        factory.create_client("s3", "us-east-1")
        factory.create_client("rds", "eu-west-1")
        factory.create_client("lambda", "ap-southeast-1")

        calls = mock_session.client.call_args_list
        assert ("s3",) == calls[0][0] or calls[0] == (("s3",), {"region_name": "us-east-1"})


class TestGetValidRegions:
    """Test region list retrieval."""

    def test_get_valid_regions_returns_configured_regions(self):
        """get_valid_regions returns the regions from settings."""
        settings = _make_settings(aws_regions=["us-east-1", "eu-west-1", "ap-southeast-1"])
        factory = AWSClientFactory(settings)
        regions = factory.get_valid_regions()
        assert regions == ["us-east-1", "eu-west-1", "ap-southeast-1"]

    def test_get_valid_regions_returns_copy(self):
        """get_valid_regions returns a new list, not a reference to settings."""
        settings = _make_settings(aws_regions=["us-east-1"])
        factory = AWSClientFactory(settings)
        regions = factory.get_valid_regions()
        regions.append("eu-west-1")
        # Original should be unchanged
        assert factory.get_valid_regions() == ["us-east-1"]

    def test_get_valid_regions_single_region(self):
        """get_valid_regions works with a single configured region."""
        settings = _make_settings(aws_regions=["us-west-2"])
        factory = AWSClientFactory(settings)
        assert factory.get_valid_regions() == ["us-west-2"]
