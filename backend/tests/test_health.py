"""Unit tests for the health check endpoint."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.routers.health import router


@pytest.fixture
def app():
    """Create a FastAPI app with the health router included."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def client(app):
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        """Health endpoint returns 200 status code."""
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_healthy_status(self, client):
        """Health endpoint returns status 'healthy'."""
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_returns_service_name(self, client):
        """Health endpoint returns correct service name."""
        response = await client.get("/health")
        data = response.json()
        assert data["service"] == "ai-cloud-cost-detective"

    @pytest.mark.asyncio
    async def test_health_response_shape(self, client):
        """Health endpoint returns exactly the expected fields."""
        response = await client.get("/health")
        data = response.json()
        assert set(data.keys()) == {"status", "service"}
