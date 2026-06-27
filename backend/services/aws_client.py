"""AWS Client Factory for creating authenticated boto3 clients.

Provides credential validation and client creation for AWS services
with clear error reporting for missing or invalid credentials.
"""

from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from backend.config.settings import Settings


class AuthenticationError(Exception):
    """Raised when AWS credentials are missing or invalid."""

    pass


class AWSClientFactory:
    """Creates authenticated boto3 clients with credential validation.

    Validates credentials via STS before allowing scans and provides
    configured boto3 clients for any AWS service/region combination.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the factory with application settings.

        Creates a boto3 session using the provided credentials. If credentials
        are not explicitly provided, boto3 will use its default credential chain
        (IAM role, instance profile, environment variables, ~/.aws/credentials).

        Args:
            settings: Application settings containing AWS credentials and config.
        """
        self._settings = settings

        # Build session kwargs — only include credentials if explicitly provided
        session_kwargs = {
            "region_name": settings.aws_default_region,
        }
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        if settings.aws_session_token:
            session_kwargs["aws_session_token"] = settings.aws_session_token

        self._session = boto3.Session(**session_kwargs)

    def validate_credentials(self) -> None:
        """Validate AWS credentials by calling STS get_caller_identity.

        Raises:
            AuthenticationError: If credentials are invalid or expired,
                including the failure reason from AWS.
        """
        try:
            sts_client = self._session.client("sts")
            sts_client.get_caller_identity()
        except NoCredentialsError:
            raise AuthenticationError(
                "AWS authentication failed: No credentials were found"
            )
        except ClientError as e:
            error_message = e.response.get("Error", {}).get(
                "Message", "Unknown error"
            )
            raise AuthenticationError(
                f"AWS authentication failed: {error_message}"
            )
        except BotoCoreError as e:
            raise AuthenticationError(
                f"AWS authentication failed: {str(e)}"
            )

    def create_client(self, service_name: str, region: str):
        """Create a boto3 client for the specified service and region.

        Args:
            service_name: The AWS service name (e.g., 'ec2', 's3', 'rds').
            region: The AWS region (e.g., 'us-east-1').

        Returns:
            A configured boto3 client for the specified service and region.
        """
        return self._session.client(service_name, region_name=region)

    def get_valid_regions(self) -> List[str]:
        """Return the list of configured regions from settings.

        Returns:
            List of validated AWS region strings from the application settings.
        """
        return list(self._settings.aws_regions)
