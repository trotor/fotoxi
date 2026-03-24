"""Tests for FastAPI routes and WebSocket."""
from __future__ import annotations

import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport

from backend.config import Config
from backend.main import create_app


@pytest_asyncio.fixture
async def app():
    """Create a test app using an in-memory SQLite database."""
    config = Config(db_path=":memory:")
    application = await create_app(config=config)
    return application


@pytest_asyncio.fixture
async def client(app):
    """Create an httpx AsyncClient with ASGI transport."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_images_empty(client):
    """GET /api/images should return empty results when no images are indexed."""
    response = await client.get("/api/images")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["images"] == []


@pytest.mark.asyncio
async def test_indexer_status(client):
    """GET /api/indexer/status should return running: false initially."""
    response = await client.get("/api/indexer/status")
    assert response.status_code == 200
    data = response.json()
    assert data["running"] is False


@pytest.mark.asyncio
async def test_get_settings(client):
    """GET /api/settings should return 200 with config fields."""
    response = await client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    # Check some expected config fields are present
    assert "ollama_url" in data
    assert "source_dirs" in data
    assert "ollama_model" in data


@pytest.mark.asyncio
async def test_get_duplicates(client):
    """GET /api/duplicates should return 200 with an empty list."""
    response = await client.get("/api/duplicates")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "groups" in data
    assert isinstance(data["groups"], list)
