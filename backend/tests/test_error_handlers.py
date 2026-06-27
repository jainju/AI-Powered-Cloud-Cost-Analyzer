"""Tests for global error handlers.

Validates that exception handlers correctly map application exceptions
to appropriate HTTP responses with sanitized error messages and correlation IDs.

Requirements: 4.6, 4.7, 5.3, 7.5
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError, BaseModel

from backend.error_handlers import register_error_handlers
from backend.exceptions import ScanInProgressError
from backend.middleware.correlation import CorrelationIdMiddleware
from backend.services.aws_client import AuthenticationError


def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with error handlers for testing."""
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)

    @app.get("/raise-auth-error")
    async def raise_auth_error():
        raise AuthenticationError("AWS authentication failed: Invalid credentials")

    @app.get("/raise-scan-in-progress")
    async def raise_scan_in_progress():
        raise ScanInProgressError()

    @app.get("/raise-scan-in-progress-custom")
    async def raise_scan_in_progress_custom():
        raise ScanInProgressError("Custom scan message")

    @app.get("/raise-validation-error")
    async def raise_validation_error():
        # Trigger a Pydantic ValidationError by validating invalid data
        class StrictModel(BaseModel):
            value: int

        StrictModel.model_validate({"value": "not_an_int"})

    @app.get("/raise-unhandled")
    async def raise_unhandled():
        raise RuntimeError("Something went wrong in /some/internal/path.py at line 42")

    @app.get("/raise-unhandled-with-class-name")
    async def raise_unhandled_with_class_name():
        raise ValueError("Error in MyInternalClass.process_data: unexpected value")

    return app


@pytest.fixture
def client():
    """Create a test client with the error handlers registered."""
    app = create_test_app()
    return TestClient(app, raise_server_exceptions=False)


class TestAuthenticationErrorHandler:
    """Tests for AuthenticationError → 401 mapping."""

    def test_returns_401_status(self, client):
        response = client.get("/raise-auth-error")
        assert response.status_code == 401

    def test_includes_error_reason(self, client):
        response = client.get("/raise-auth-error")
        body = response.json()
        assert "error" in body
        assert "AWS authentication failed" in body["error"]

    def test_includes_correlation_id(self, client):
        response = client.get("/raise-auth-error")
        body = response.json()
        assert "correlation_id" in body
        assert body["correlation_id"] is not None


class TestScanInProgressErrorHandler:
    """Tests for ScanInProgressError → 429 mapping."""

    def test_returns_429_status(self, client):
        response = client.get("/raise-scan-in-progress")
        assert response.status_code == 429

    def test_includes_default_message(self, client):
        response = client.get("/raise-scan-in-progress")
        body = response.json()
        assert body["error"] == "A scan is already in progress"

    def test_includes_custom_message(self, client):
        response = client.get("/raise-scan-in-progress-custom")
        body = response.json()
        assert body["error"] == "Custom scan message"

    def test_includes_correlation_id(self, client):
        response = client.get("/raise-scan-in-progress")
        body = response.json()
        assert "correlation_id" in body
        assert body["correlation_id"] is not None


class TestValidationErrorHandler:
    """Tests for Pydantic ValidationError → 500 mapping."""

    def test_returns_500_status(self, client):
        response = client.get("/raise-validation-error")
        assert response.status_code == 500

    def test_returns_generic_message(self, client):
        response = client.get("/raise-validation-error")
        body = response.json()
        assert body["error"] == "Internal response error"

    def test_does_not_expose_model_details(self, client):
        response = client.get("/raise-validation-error")
        body = response.json()
        # Should not contain field names or validation details
        assert "StrictModel" not in str(body)
        assert "value" not in body["error"]

    def test_includes_correlation_id(self, client):
        response = client.get("/raise-validation-error")
        body = response.json()
        assert "correlation_id" in body
        assert body["correlation_id"] is not None


class TestUnhandledExceptionHandler:
    """Tests for unhandled exceptions → 500 mapping."""

    def test_returns_500_status(self, client):
        response = client.get("/raise-unhandled")
        assert response.status_code == 500

    def test_returns_generic_message(self, client):
        response = client.get("/raise-unhandled")
        body = response.json()
        assert body["error"] == "An internal error occurred"

    def test_does_not_expose_stack_traces(self, client):
        response = client.get("/raise-unhandled")
        body = response.json()
        # Should not contain file paths or stack trace info
        assert "path.py" not in str(body)
        assert "line 42" not in str(body)
        assert "Traceback" not in str(body)

    def test_does_not_expose_file_paths(self, client):
        response = client.get("/raise-unhandled")
        body = response.json()
        assert "/some/internal/" not in str(body)

    def test_does_not_expose_class_names(self, client):
        response = client.get("/raise-unhandled-with-class-name")
        body = response.json()
        assert "MyInternalClass" not in str(body)
        assert "process_data" not in str(body)

    def test_includes_correlation_id(self, client):
        response = client.get("/raise-unhandled")
        body = response.json()
        assert "correlation_id" in body
        assert body["correlation_id"] is not None

    def test_correlation_id_matches_header(self, client):
        response = client.get("/raise-unhandled")
        body = response.json()
        header_id = response.headers.get("X-Correlation-ID")
        # The correlation ID in the body should match the one in headers
        assert body["correlation_id"] == header_id
