"""Configuration management using Pydantic Settings.

Loads configuration from environment variables and .env file,
with environment variables taking precedence over .env values.
"""

import re
from typing import List, Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


# Valid AWS region name pattern (e.g., us-east-1, eu-west-2, ap-southeast-1)
AWS_REGION_PATTERN = re.compile(r"^[a-z]{2}(-[a-z]+-\d+)$")


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    Environment variables take precedence over values in the .env file.
    Required fields (aws_access_key_id, aws_secret_access_key) must be set
    or the application will fail to start with a validation error identifying
    each missing variable by name.
    """

    # AWS credentials (optional — if not set, boto3 uses the default credential chain:
    # IAM role, instance profile, environment variables, ~/.aws/credentials, etc.)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_default_region: str = "us-east-1"
    aws_session_token: Optional[str] = None

    # Scan configuration
    aws_regions: List[str] = ["us-east-1"]
    max_concurrent_api_calls: int = 10
    max_retry_attempts: int = 3
    scan_timeout_seconds: int = 300

    # Application
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @field_validator("aws_regions", mode="before")
    @classmethod
    def parse_regions(cls, v):
        """Parse comma-separated region strings into a list."""
        if isinstance(v, str):
            return [r.strip() for r in v.split(",") if r.strip()]
        return v

    @field_validator("aws_regions", mode="after")
    @classmethod
    def validate_region_names(cls, v):
        """Validate that each region name matches the AWS region format."""
        invalid_regions = []
        for region in v:
            if not AWS_REGION_PATTERN.match(region):
                invalid_regions.append(region)
        if invalid_regions:
            raise ValueError(
                f"Invalid AWS region name(s): {', '.join(invalid_regions)}. "
                f"Region names must match the format like 'us-east-1', 'eu-west-2'."
            )
        if len(v) < 1 or len(v) > 30:
            raise ValueError(
                "aws_regions must contain between 1 and 30 regions."
            )
        return v

    @field_validator("aws_default_region")
    @classmethod
    def validate_default_region(cls, v):
        """Validate the default region name format."""
        if not AWS_REGION_PATTERN.match(v):
            raise ValueError(
                f"Invalid AWS region name: '{v}'. "
                f"Region names must match the format like 'us-east-1', 'eu-west-2'."
            )
        return v

    @field_validator("max_concurrent_api_calls")
    @classmethod
    def validate_max_concurrent_api_calls(cls, v):
        """Validate that max_concurrent_api_calls is a positive integer."""
        if v <= 0:
            raise ValueError(
                f"max_concurrent_api_calls must be a positive integer, got {v}. "
                f"Accepted values: integers greater than 0."
            )
        return v

    @field_validator("max_retry_attempts")
    @classmethod
    def validate_max_retry_attempts(cls, v):
        """Validate that max_retry_attempts is a positive integer."""
        if v <= 0:
            raise ValueError(
                f"max_retry_attempts must be a positive integer, got {v}. "
                f"Accepted values: integers greater than 0."
            )
        return v

    @field_validator("scan_timeout_seconds")
    @classmethod
    def validate_scan_timeout_seconds(cls, v):
        """Validate that scan_timeout_seconds is a positive integer."""
        if v <= 0:
            raise ValueError(
                f"scan_timeout_seconds must be a positive integer, got {v}. "
                f"Accepted values: integers greater than 0."
            )
        return v
