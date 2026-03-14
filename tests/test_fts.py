"""Tests for database session initialisation and FTS5 full-text search (Task 3)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Image
from backend.db.session import create_engine_and_init


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """Create a fresh in-memory database with FTS5 initialised."""
    engine, factory = await create_engine_and_init(":memory:")
    yield engine, factory
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db):
    """Yield an AsyncSession bound to the in-memory database."""
    engine, factory = db
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Session / init_db tests
# ---------------------------------------------------------------------------


async def test_create_engine_returns_engine_and_factory(db) -> None:
    """create_engine_and_init returns a 2-tuple of engine and session factory."""
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

    engine, factory = db
    assert isinstance(engine, AsyncEngine)
    assert isinstance(factory, async_sessionmaker)


async def test_fts_table_exists(session: AsyncSession) -> None:
    """The images_fts virtual table is present after init."""
    result = await session.execute(
        text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='images_fts'"
        )
    )
    row = result.scalar_one_or_none()
    assert row == "images_fts", "FTS5 virtual table 'images_fts' was not created"


async def test_orm_tables_exist(session: AsyncSession) -> None:
    """All ORM tables are created by create_engine_and_init."""
    result = await session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    )
    tables = {row[0] for row in result.fetchall()}
    assert "images" in tables
    assert "duplicate_groups" in tables
    assert "duplicate_group_members" in tables
    assert "settings" in tables


# ---------------------------------------------------------------------------
# FTS5 search tests
# ---------------------------------------------------------------------------


async def _insert_image_and_sync_fts(
    session: AsyncSession,
    *,
    file_path: str,
    file_name: str,
    ai_description: str = "",
    ai_tags: str = "",
) -> Image:
    """Helper: insert an Image and manually sync it into the FTS index."""
    img = Image(
        file_path=file_path,
        file_name=file_name,
        file_size=1024,
        file_mtime=1700000000.0,
        ai_description=ai_description or None,
        ai_tags=ai_tags or None,
        status="indexed",
    )
    session.add(img)
    await session.flush()  # get the rowid

    # Manually populate the FTS index (content table sync)
    await session.execute(
        text(
            "INSERT INTO images_fts(rowid, ai_description, ai_tags, file_name) "
            "VALUES (:rowid, :desc, :tags, :fname)"
        ),
        {
            "rowid": img.id,
            "desc": ai_description,
            "tags": ai_tags,
            "fname": file_name,
        },
    )
    await session.commit()
    return img


async def test_fts_search_by_ai_description(session: AsyncSession) -> None:
    """Inserting an image with an ai_description makes it findable via FTS."""
    img = await _insert_image_and_sync_fts(
        session,
        file_path="/photos/mountain.jpg",
        file_name="mountain.jpg",
        ai_description="A majestic snow-capped mountain at sunrise",
        ai_tags='["mountain", "snow", "sunrise"]',
    )

    result = await session.execute(
        text("SELECT rowid FROM images_fts WHERE images_fts MATCH 'majestic'")
    )
    rows = result.fetchall()
    rowids = [r[0] for r in rows]
    assert img.id in rowids, f"Expected image id {img.id} in FTS results {rowids}"


async def test_fts_search_by_ai_tags(session: AsyncSession) -> None:
    """An image is findable via a keyword in its ai_tags field."""
    img = await _insert_image_and_sync_fts(
        session,
        file_path="/photos/beach.jpg",
        file_name="beach.jpg",
        ai_description="People relaxing on a sandy shore",
        ai_tags='["beach", "ocean", "summer"]',
    )

    result = await session.execute(
        text("SELECT rowid FROM images_fts WHERE images_fts MATCH 'ocean'")
    )
    rows = result.fetchall()
    rowids = [r[0] for r in rows]
    assert img.id in rowids


async def test_fts_search_by_file_name(session: AsyncSession) -> None:
    """An image is findable via a token in its file_name."""
    img = await _insert_image_and_sync_fts(
        session,
        file_path="/photos/sunset_panorama.jpg",
        file_name="sunset_panorama.jpg",
        ai_description="Golden hour over the horizon",
        ai_tags='["sunset"]',
    )

    result = await session.execute(
        text("SELECT rowid FROM images_fts WHERE images_fts MATCH 'sunset'")
    )
    rows = result.fetchall()
    rowids = [r[0] for r in rows]
    assert img.id in rowids


async def test_fts_no_match_returns_empty(session: AsyncSession) -> None:
    """A search for a term that does not appear in any image returns no rows."""
    await _insert_image_and_sync_fts(
        session,
        file_path="/photos/forest.jpg",
        file_name="forest.jpg",
        ai_description="Dense green forest with tall trees",
        ai_tags='["forest", "trees", "nature"]',
    )

    result = await session.execute(
        text("SELECT rowid FROM images_fts WHERE images_fts MATCH 'xyzuniqueterm99'")
    )
    rows = result.fetchall()
    assert rows == [], f"Expected no FTS results but got {rows}"


async def test_fts_multiple_images_only_matching_returned(session: AsyncSession) -> None:
    """Only the image whose content matches is returned, not all images."""
    img_cat = await _insert_image_and_sync_fts(
        session,
        file_path="/photos/cat.jpg",
        file_name="cat.jpg",
        ai_description="A fluffy orange cat sitting on a windowsill",
        ai_tags='["cat", "pet"]',
    )
    await _insert_image_and_sync_fts(
        session,
        file_path="/photos/dog.jpg",
        file_name="dog.jpg",
        ai_description="A golden retriever playing in the park",
        ai_tags='["dog", "pet"]',
    )

    result = await session.execute(
        text("SELECT rowid FROM images_fts WHERE images_fts MATCH 'fluffy'")
    )
    rows = result.fetchall()
    rowids = [r[0] for r in rows]
    assert img_cat.id in rowids
    assert len(rowids) == 1, f"Expected 1 result but got {len(rowids)}: {rowids}"
