"""Unit tests for the correlation ID middleware."""

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from backend.middleware.correlation import (
    CorrelationIdMiddleware,
    correlation_id_ctx,
    get_correlation_id,
)


@pytest.fixture
def app():
    """Create a FastAPI app with the correlation ID middleware."""
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {
            "correlation_id_from_state": request.state.correlation_id,
            "correlation_id_from_context": get_correlation_id(),
        }

    @app.get("/nested")
    async def nested_endpoint(request: Request):
        """Endpoint that calls get_correlation_id from a nested function."""
        def inner():
            return get_correlation_id()

        return {"correlation_id": inner()}

    return app


@pytest.fixture
async def client(app):
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestCorrelationIdMiddleware:
    """Tests for CorrelationIdMiddleware."""

    @pytest.mark.asyncio
    async def test_generates_uuid_per_request(self, client):
        """Each request gets a unique UUID correlation ID."""
        response = await client.get("/test")
        assert response.status_code == 200

        data = response.json()
        correlation_id = data["correlation_id_from_state"]

        # Verify it's a valid UUID
        parsed = uuid.UUID(correlation_id)
        assert str(parsed) == correlation_id

    @pytest.mark.asyncio
    async def test_correlation_id_in_response_header(self, client):
        """Correlation ID is included in response X-Correlation-ID header."""
        response = await client.get("/test")
        assert "X-Correlation-ID" in response.headers

        header_id = response.headers["X-Correlation-ID"]
        body_id = response.json()["correlation_id_from_state"]
        assert header_id == body_id

    @pytest.mark.asyncio
    async def test_state_and_context_have_same_id(self, client):
        """Request state and context variable hold the same correlation ID."""
        response = await client.get("/test")
        data = response.json()

        assert data["correlation_id_from_state"] == data["correlation_id_from_context"]

    @pytest.mark.asyncio
    async def test_different_requests_get_different_ids(self, client):
        """Two separate requests get different correlation IDs."""
        response1 = await client.get("/test")
        response2 = await client.get("/test")

        id1 = response1.json()["correlation_id_from_state"]
        id2 = response2.json()["correlation_id_from_state"]

        assert id1 != id2

    @pytest.mark.asyncio
    async def test_context_variable_accessible_in_nested_calls(self, client):
        """Correlation ID is accessible from nested function calls via context var."""
        response = await client.get("/nested")
        data = response.json()

        correlation_id = data["correlation_id"]
        # Verify it's a valid UUID
        uuid.UUID(correlation_id)
        assert correlation_id is not None

    @pytest.mark.asyncio
    async def test_context_variable_reset_after_request(self, client):
        """Context variable is reset after request completes."""
        await client.get("/test")

        # After the request, the context variable should be None
        assert get_correlation_id() is None

    @pytest.mark.asyncio
    async def test_correlation_id_is_uuid4_format(self, client):
        """Generated correlation ID is a valid UUID4."""
        response = await client.get("/test")
        correlation_id = response.json()["correlation_id_from_state"]

        parsed = uuid.UUID(correlation_id, version=4)
        assert parsed.version == 4


class TestGetCorrelationId:
    """Tests for the get_correlation_id helper function."""

    def test_returns_none_outside_request_context(self):
        """Returns None when no request is being processed."""
        assert get_correlation_id() is None

    def test_returns_value_when_context_is_set(self):
        """Returns the correlation ID when explicitly set in context."""
        test_id = "test-correlation-id-123"
        token = correlation_id_ctx.set(test_id)
        try:
            assert get_correlation_id() == test_id
        finally:
            correlation_id_ctx.reset(token)
