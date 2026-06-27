"""Validation tests for configuration management (task 1.2)."""

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.config.settings import Settings


class TestSettingsBasic:
    """Test basic Settings instantiation and defaults."""

    def test_valid_settings_with_defaults(self, monkeypatch):
        """Settings can be created with required fields and defaults applied."""
        # Clear env vars that could override defaults
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        monkeypatch.delenv("AWS_REGIONS", raising=False)
        monkeypatch.delenv("MAX_CONCURRENT_API_CALLS", raising=False)
        monkeypatch.delenv("MAX_RETRY_ATTEMPTS", raising=False)
        monkeypatch.delenv("SCAN_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        settings = Settings(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            _env_file=None,
        )
        assert settings.aws_access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert settings.aws_secret_access_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert settings.aws_default_region == "us-east-1"
        assert settings.aws_session_token is None
        assert settings.aws_regions == ["us-east-1"]
        assert settings.max_concurrent_api_calls == 10
        assert settings.max_retry_attempts == 3
        assert settings.scan_timeout_seconds == 300
        assert settings.log_level == "INFO"

    def test_all_fields_specified(self):
        """Settings can be created with all fields explicitly provided."""
        settings = Settings(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            aws_default_region="eu-west-1",
            aws_session_token="FwoGZXIvYXdzEBY",
            aws_regions=["us-east-1", "eu-west-1"],
            max_concurrent_api_calls=5,
            max_retry_attempts=5,
            scan_timeout_seconds=600,
            log_level="DEBUG",
        )
        assert settings.aws_default_region == "eu-west-1"
        assert settings.aws_session_token == "FwoGZXIvYXdzEBY"
        assert settings.aws_regions == ["us-east-1", "eu-west-1"]
        assert settings.max_concurrent_api_calls == 5
        assert settings.max_retry_attempts == 5
        assert settings.scan_timeout_seconds == 600
        assert settings.log_level == "DEBUG"


class TestRegionValidation:
    """Test region name validation and parsing."""

    def test_comma_separated_regions_parsed(self):
        """Comma-separated string is parsed into a list of regions."""
        settings = Settings(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="secret",
            aws_regions="us-east-1,eu-west-1,ap-southeast-1",
        )
        assert settings.aws_regions == ["us-east-1", "eu-west-1", "ap-southeast-1"]

    def test_comma_separated_with_spaces(self):
        """Comma-separated string with spaces is trimmed and parsed."""
        settings = Settings(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="secret",
            aws_regions="us-east-1, eu-west-1 , ap-southeast-1",
        )
        assert settings.aws_regions == ["us-east-1", "eu-west-1", "ap-southeast-1"]

    def test_invalid_region_name_raises_error(self):
        """Invalid region names cause a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                aws_regions=["invalid-region"],
            )
        assert "Invalid AWS region name" in str(exc_info.value)

    def test_invalid_default_region_raises_error(self):
        """Invalid default region causes a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                aws_default_region="not-a-region",
            )
        assert "Invalid AWS region name" in str(exc_info.value)

    def test_valid_regions(self):
        """Various valid AWS region formats are accepted."""
        settings = Settings(
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="secret",
            aws_regions=["us-east-1", "us-west-2", "eu-central-1", "ap-northeast-1"],
        )
        assert len(settings.aws_regions) == 4


class TestRateLimitingValidation:
    """Test positive integer validation for rate limiting parameters."""

    def test_zero_concurrent_calls_raises_error(self):
        """Zero max_concurrent_api_calls raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                max_concurrent_api_calls=0,
            )
        assert "max_concurrent_api_calls" in str(exc_info.value)

    def test_negative_concurrent_calls_raises_error(self):
        """Negative max_concurrent_api_calls raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                max_concurrent_api_calls=-1,
            )
        assert "max_concurrent_api_calls" in str(exc_info.value)

    def test_zero_retry_attempts_raises_error(self):
        """Zero max_retry_attempts raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                max_retry_attempts=0,
            )
        assert "max_retry_attempts" in str(exc_info.value)

    def test_negative_timeout_raises_error(self):
        """Negative scan_timeout_seconds raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                scan_timeout_seconds=-100,
            )
        assert "scan_timeout_seconds" in str(exc_info.value)


class TestLogLevelValidation:
    """Test log level validation."""

    def test_valid_log_levels(self):
        """All valid log levels are accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                log_level=level,
            )
            assert settings.log_level == level

    def test_invalid_log_level_raises_error(self):
        """Invalid log level raises a validation error."""
        with pytest.raises(ValidationError):
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="secret",
                log_level="VERBOSE",
            )


class TestMissingRequiredFields:
    """Test behavior when required fields are missing."""

    def test_missing_access_key_raises_error(self, monkeypatch):
        """Missing aws_access_key_id raises a validation error naming the field."""
        # Clear environment variables that might provide values
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_secret_access_key="secret",
                _env_file=None,
            )
        assert "aws_access_key_id" in str(exc_info.value)

    def test_missing_secret_key_raises_error(self, monkeypatch):
        """Missing aws_secret_access_key raises a validation error naming the field."""
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                _env_file=None,
            )
        assert "aws_secret_access_key" in str(exc_info.value)


class TestEnvFileLoading:
    """Test .env file loading configuration."""

    def test_env_file_configured(self):
        """Settings class is configured to load from .env file."""
        assert Settings.model_config.get("env_file") == ".env"
        assert Settings.model_config.get("env_file_encoding") == "utf-8"
