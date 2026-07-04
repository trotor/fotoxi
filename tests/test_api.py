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


@pytest.mark.asyncio
async def test_bulk_resolve_duplicates_dry_run(app, client):
    """POST /api/duplicates/bulk-resolve dry-run reports a resolvable copy group."""
    from backend.db.models import Image, DuplicateGroup, DuplicateGroupMember

    factory = app.state.session_factory
    async with factory() as s:
        a = Image(file_path="/p/a.jpg", file_name="a.jpg", file_size=100,
                  file_mtime=1.0, width=1000, height=1000, status="indexed")
        b = Image(file_path="/p/b.jpg", file_name="b.jpg", file_size=100,
                  file_mtime=2.0, width=2000, height=2000, status="indexed")
        s.add_all([a, b])
        await s.flush()
        g = DuplicateGroup(match_type="exact")
        s.add(g)
        await s.flush()
        s.add(DuplicateGroupMember(group_id=g.id, image_id=a.id, is_best=False))
        s.add(DuplicateGroupMember(group_id=g.id, image_id=b.id, is_best=True))
        await s.commit()

    resp = await client.post("/api/duplicates/bulk-resolve", json={"dry_run": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["groups"] == 1
    assert data["rejected"] == 1
    assert data["applied"] is False
