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


@pytest.mark.asyncio
async def test_unresolve_duplicate_group(app, client):
    """POST /api/duplicates/{id}/unresolve restores prior statuses and clears choices."""
    from sqlalchemy import select
    from backend.db.models import Image, DuplicateGroup, DuplicateGroupMember

    factory = app.state.session_factory
    async with factory() as s:
        a = Image(file_path="/p/a.jpg", file_name="a.jpg", file_size=100,
                  file_mtime=1.0, width=1000, height=1000, status="indexed")
        b = Image(file_path="/p/b.jpg", file_name="b.jpg", file_size=100,
                  file_mtime=2.0, width=2000, height=2000, status="indexed")
        s.add_all([a, b])
        await s.flush()
        g = DuplicateGroup(match_type="burst")
        s.add(g)
        await s.flush()
        s.add(DuplicateGroupMember(group_id=g.id, image_id=a.id, is_best=False))
        s.add(DuplicateGroupMember(group_id=g.id, image_id=b.id, is_best=True))
        await s.commit()
        group_id, a_id, b_id = g.id, a.id, b.id

    # Resolve: keep b, reject a.
    resp = await client.post(
        f"/api/duplicates/{group_id}/resolve", json={"keep": [b_id], "reject": [a_id]}
    )
    assert resp.status_code == 200

    # Undo it, restoring both to their previous "indexed" status.
    resp = await client.post(
        f"/api/duplicates/{group_id}/unresolve",
        json={"statuses": {str(a_id): "indexed", str(b_id): "indexed"}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "unresolved"

    async with factory() as s:
        rows = (await s.execute(select(Image).where(Image.id.in_([a_id, b_id])))).scalars().all()
        assert {r.status for r in rows} == {"indexed"}
        assert all(r.rejected_at is None and r.kept_at is None for r in rows)

        members = (
            await s.execute(
                select(DuplicateGroupMember).where(DuplicateGroupMember.group_id == group_id)
            )
        ).scalars().all()
        assert all(m.user_choice is None for m in members)


@pytest.mark.asyncio
async def test_unresolve_unknown_group_returns_404(client):
    """POST /api/duplicates/{id}/unresolve returns 404 for a group that doesn't exist."""
    resp = await client.post("/api/duplicates/99999/unresolve", json={"statuses": {}})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_version_endpoint(client):
    """GET /api/version returns the app version from pyproject (single source)."""
    import tomllib
    from pathlib import Path

    resp = await client.get("/api/version")
    assert resp.status_code == 200
    data = resp.json()
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    assert data["version"] == expected


@pytest.mark.asyncio
async def test_errors_summary_and_retry_endpoints(app, client):
    """GET /api/errors/summary groups by cause; POST /api/errors/retry resets them."""
    from backend.db.models import Image

    factory = app.state.session_factory
    async with factory() as s:
        s.add(Image(file_path="/e1.jpg", file_name="e1.jpg", file_size=1, file_mtime=1.0,
                    status="error", error_message="AI analysis returned no result"))
        s.add(Image(file_path="/e2.jpg", file_name="e2.jpg", file_size=1, file_mtime=1.0,
                    status="error", error_message="AI analysis returned no result"))
        s.add(Image(file_path="/m1.jpg", file_name="m1.jpg", file_size=1, file_mtime=1.0,
                    status="missing"))
        await s.commit()

    resp = await client.get("/api/errors/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_errors"] == 2
    assert data["total_missing"] == 1
    assert data["causes"][0]["cause"] == "AI analysis returned no result"
    assert data["causes"][0]["count"] == 2

    retry = await client.post("/api/errors/retry", json={})
    assert retry.status_code == 200
    assert retry.json()["reset"] == 2

    # after retry, no errors remain
    resp2 = await client.get("/api/errors/summary")
    assert resp2.json()["total_errors"] == 0
