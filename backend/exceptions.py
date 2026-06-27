"""Application-level exceptions for the AI Cloud Cost Detective backend.

Provides custom exception classes used across the application for
well-defined error conditions with appropriate HTTP status mappings.
"""


class ScanInProgressError(Exception):
    """Raised when a scan is requested while another scan is already running.

    Maps to HTTP 429 (Too Many Requests) in the error handler.
    """

    def __init__(self, message: str = "A scan is already in progress") -> None:
        self.message = message
        super().__init__(self.message)
