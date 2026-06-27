"""Tests for the request logging middleware."""

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from backend.middleware.request_logging import RequestLoggingMiddleware


@pytest.fixture
def app():
    """Create a test FastAPI app with request logging middleware."""
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app):
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_request_logging_logs_info_level(app, client, caplog):
    """Test that request logging middleware logs at INFO level."""
    with caplog.at_level(logging.INFO, logger="backend.middleware.request_logging"):
        response = await client.get("/test")

    assert response.status_code == 200
    # Check that a log entry was created with method, path, status code
    log_records = [
        r for r in caplog.records
        if r.name == "backend.middleware.request_logging"
    ]
    assert len(log_records) >= 1
    record = log_records[0]
    assert record.levelno == logging.INFO
    assert "GET" in record.message
    assert "/test" in record.message
    assert "200" in record.message


@pytest.mark.asyncio
async def test_request_logging_includes_response_time(app, client, caplog):
    """Test that request logging middleware includes response time in ms."""
    with caplog.at_level(logging.INFO, logger="backend.middleware.request_logging"):
        await client.get("/test")

    log_records = [
        r for r in caplog.records
        if r.name == "backend.middleware.request_logging"
    ]
    assert len(log_records) >= 1
    # Response time should contain 'ms'
    assert "ms" in log_records[0].message


@pytest.mark.asyncio
async def test_request_logging_captures_status_code_404(app, client, caplog):
    """Test that the middleware logs the correct status code for 404."""
    with caplog.at_level(logging.INFO, logger="backend.middleware.request_logging"):
        response = await client.get("/nonexistent")

    assert response.status_code == 404
    log_records = [
        r for r in caplog.records
        if r.name == "backend.middleware.request_logging"
    ]
    assert len(log_records) >= 1
    assert "404" in log_records[0].message
    assert "GET" in log_records[0].message
    assert "/nonexistent" in log_records[0].message
