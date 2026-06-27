"""Structured JSON logging configuration for the AI Cloud Cost Detective backend.

Provides a JSON formatter that ensures every log entry includes:
- timestamp (ISO 8601 format)
- level (log level name)
- correlation_id (from contextvars or 'N/A' if not in a request context)
- message (the log message)

Additional fields from the `extra` dict are merged into the JSON output.

Log level conventions:
- ERROR: failures and exceptions
- WARNING: retries and degraded operations
- INFO: request lifecycle events (received, completed)
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional


# Context variable to hold the correlation ID for the current request
correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


class StructuredJSONFormatter(logging.Formatter):
    """A log formatter that outputs structured JSON log entries.

    Each log entry contains at minimum:
    - timestamp: ISO 8601 formatted timestamp
    - level: The log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - correlation_id: The request correlation ID or null
    - message: The log message

    Any extra fields passed via the `extra` kwarg in logging calls
    are merged into the top-level JSON object.
    """

    # Fields that are part of the standard LogRecord and should not be
    # included as extra fields in the JSON output.
    _RESERVED_ATTRS = frozenset(
        {
            "args",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A JSON-formatted string containing the structured log entry.
        """
        # Build the base log entry with required fields
        log_entry = {
            "timestamp": self._format_timestamp(record),
            "level": record.levelname,
            "correlation_id": correlation_id_var.get(None),
            "message": record.getMessage(),
        }

        # Add logger name for traceability
        log_entry["logger"] = record.name

        # Merge any extra fields from the record
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS and key not in log_entry:
                log_entry[key] = value

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_entry, default=str)

    def _format_timestamp(self, record: logging.LogRecord) -> str:
        """Format the log record timestamp as ISO 8601.

        Args:
            record: The log record.

        Returns:
            ISO 8601 formatted timestamp string.
        """
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.isoformat()


def setup_logging(log_level: str = "INFO") -> None:
    """Configure the application's structured JSON logging.

    Sets up the root logger with a StreamHandler writing to stdout,
    using the StructuredJSONFormatter. The log level is configurable
    via the `log_level` parameter, which integrates with the Settings
    class's `log_level` field.

    Args:
        log_level: The minimum log level to output. Must be one of
            DEBUG, INFO, WARNING, ERROR, CRITICAL. Defaults to INFO.
    """
    # Get the numeric level, defaulting to INFO if invalid
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create the JSON formatter
    formatter = StructuredJSONFormatter()

    # Configure the stream handler (stdout for structured log collection)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(numeric_level)

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove any existing handlers to avoid duplicate output
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    This is a convenience function that returns a standard library logger.
    The structured JSON formatting is applied via the root logger's handler
    configured by `setup_logging()`.

    Args:
        name: The logger name, typically `__name__` of the calling module.

    Returns:
        A configured Logger instance.
    """
    return logging.getLogger(name)
