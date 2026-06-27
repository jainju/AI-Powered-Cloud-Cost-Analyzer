"""Tests for structured JSON logging configuration.

Verifies that:
- Log entries are valid JSON with required fields (timestamp, level, correlation_id, message)
- Timestamp is in ISO 8601 format
- Correlation ID from context variable is included
- Extra fields are merged into log output
- Log level filtering works correctly
- setup_logging integrates with Settings log_level
"""

import json
import logging
from datetime import datetime
from io import StringIO
from unittest.mock import patch

import pytest

from backend.config.logging import (
    StructuredJSONFormatter,
    correlation_id_var,
    get_logger,
    setup_logging,
)


class TestStructuredJSONFormatter:
    """Tests for the StructuredJSONFormatter class."""

    def setup_method(self):
        """Set up a logger with StructuredJSONFormatter for each test."""
        self.formatter = StructuredJSONFormatter()
        self.handler = logging.StreamHandler(StringIO())
        self.handler.setFormatter(self.formatter)
        self.logger = logging.getLogger("test.structured_json")
        self.logger.handlers.clear()
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)

    def _get_log_output(self) -> dict:
        """Get the last log entry as a parsed dict."""
        output = self.handler.stream.getvalue().strip()
        # Get the last line in case of multiple log entries
        last_line = output.split("\n")[-1]
        return json.loads(last_line)

    def test_log_entry_is_valid_json(self):
        """Log output should be valid JSON."""
        self.logger.info("Test message")
        output = self.handler.stream.getvalue().strip()
        # Should not raise
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self):
        """Every log entry must include timestamp, level, correlation_id, message."""
        self.logger.info("Hello world")
        entry = self._get_log_output()

        assert "timestamp" in entry
        assert "level" in entry
        assert "correlation_id" in entry
        assert "message" in entry

    def test_timestamp_is_iso8601(self):
        """Timestamp should be in ISO 8601 format."""
        self.logger.info("Timestamp test")
        entry = self._get_log_output()

        # Should parse without error as ISO 8601
        ts = entry["timestamp"]
        parsed_dt = datetime.fromisoformat(ts)
        assert parsed_dt is not None

    def test_level_matches_log_level(self):
        """Level field should match the log level used."""
        self.logger.info("Info message")
        entry = self._get_log_output()
        assert entry["level"] == "INFO"

        # Clear and log at ERROR
        self.handler.stream = StringIO()
        self.logger.error("Error message")
        entry = self._get_log_output()
        assert entry["level"] == "ERROR"

    def test_message_content(self):
        """Message field should contain the log message."""
        self.logger.info("My specific message")
        entry = self._get_log_output()
        assert entry["message"] == "My specific message"

    def test_correlation_id_null_when_not_set(self):
        """Correlation ID should be null when not in a request context."""
        # Reset the context var
        token = correlation_id_var.set(None)
        try:
            self.logger.info("No correlation")
            entry = self._get_log_output()
            assert entry["correlation_id"] is None
        finally:
            correlation_id_var.reset(token)

    def test_correlation_id_from_context(self):
        """Correlation ID should come from the context variable when set."""
        token = correlation_id_var.set("test-corr-id-123")
        try:
            self.logger.info("With correlation")
            entry = self._get_log_output()
            assert entry["correlation_id"] == "test-corr-id-123"
        finally:
            correlation_id_var.reset(token)

    def test_extra_fields_merged(self):
        """Extra fields passed via the extra kwarg should be in the JSON output."""
        self.logger.warning(
            "Retry happening",
            extra={"service": "ec2", "attempt": 2, "delay_seconds": 2.0},
        )
        entry = self._get_log_output()
        assert entry["service"] == "ec2"
        assert entry["attempt"] == 2
        assert entry["delay_seconds"] == 2.0

    def test_exception_info_included(self):
        """Exception info should be included when logging with exc_info."""
        try:
            raise ValueError("Something went wrong")
        except ValueError:
            self.logger.error("Caught error", exc_info=True)

        entry = self._get_log_output()
        assert "exception" in entry
        assert "ValueError" in entry["exception"]
        assert "Something went wrong" in entry["exception"]

    def test_logger_name_included(self):
        """Logger name should be in the log entry for traceability."""
        self.logger.info("Logger name test")
        entry = self._get_log_output()
        assert entry["logger"] == "test.structured_json"


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def teardown_method(self):
        """Reset root logger after each test."""
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_setup_logging_configures_root_logger(self):
        """setup_logging should configure the root logger with JSON formatter."""
        setup_logging("INFO")
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, StructuredJSONFormatter)

    def test_setup_logging_sets_level(self):
        """setup_logging should set the root logger to the specified level."""
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

        setup_logging("ERROR")
        root = logging.getLogger()
        assert root.level == logging.ERROR

    def test_setup_logging_default_info(self):
        """setup_logging should default to INFO level."""
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_setup_logging_clears_existing_handlers(self):
        """setup_logging should remove existing handlers to prevent duplicates."""
        setup_logging("INFO")
        root = logging.getLogger()
        # After setup_logging, there should be exactly one handler
        # (the one we installed), regardless of what was there before
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, StructuredJSONFormatter)

    def test_setup_logging_reduces_third_party_noise(self):
        """Third-party library loggers should be set to WARNING or higher."""
        setup_logging("DEBUG")
        assert logging.getLogger("botocore").level == logging.WARNING
        assert logging.getLogger("boto3").level == logging.WARNING
        assert logging.getLogger("urllib3").level == logging.WARNING


class TestGetLogger:
    """Tests for the get_logger convenience function."""

    def test_returns_logger_with_name(self):
        """get_logger should return a logger with the specified name."""
        logger = get_logger("my.module")
        assert logger.name == "my.module"
        assert isinstance(logger, logging.Logger)


class TestLogLevelConventions:
    """Tests verifying log level conventions per Requirement 7.6.

    - ERROR for failures and exceptions
    - WARNING for retries and degraded operations
    - INFO for request lifecycle events
    """

    def setup_method(self):
        """Set up a logger with a capturing handler."""
        self.formatter = StructuredJSONFormatter()
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(self.formatter)
        self.logger = logging.getLogger("test.log_levels")
        self.logger.handlers.clear()
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)

    def _get_all_entries(self) -> list:
        """Get all log entries from the stream."""
        output = self.stream.getvalue().strip()
        if not output:
            return []
        return [json.loads(line) for line in output.split("\n")]

    def test_error_for_failures(self):
        """Failures should be logged at ERROR level."""
        self.logger.error(
            "Service scan failed",
            extra={"service": "ec2", "region": "us-east-1", "error": "AccessDenied"},
        )
        entries = self._get_all_entries()
        assert entries[0]["level"] == "ERROR"

    def test_warning_for_retries(self):
        """Retries should be logged at WARNING level."""
        self.logger.warning(
            "Throttled by AWS API. Retrying.",
            extra={"service": "ec2", "operation": "describe_instances", "attempt": 1},
        )
        entries = self._get_all_entries()
        assert entries[0]["level"] == "WARNING"

    def test_info_for_request_lifecycle(self):
        """Request lifecycle events should be logged at INFO level."""
        self.logger.info(
            "Request received",
            extra={"method": "POST", "path": "/api/v1/resources/scan"},
        )
        entries = self._get_all_entries()
        assert entries[0]["level"] == "INFO"
