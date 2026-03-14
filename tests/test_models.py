"""Tests for SQLAlchemy ORM models (Task 2)."""
from __future__ import annotations

import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db.models import Base, DuplicateGroup, DuplicateGroupMember, Image, Setting


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Provide a fresh in-memory SQLite session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    await engine.dispose()


# ---------------------------------------------------------------------------
# Image tests
# ---------------------------------------------------------------------------


async def test_create_image_minimal(session: AsyncSession) -> None:
    """An Image with only required fields can be persisted and retrieved."""
    img = Image(
        file_path="/photos/test.jpg",
        file_name="test.jpg",
        file_size=1024,
        file_mtime=1700000000.0,
    )
    session.add(img)
    await session.commit()
    await session.refresh(img)

    assert img.id is not None
    assert img.file_path == "/photos/test.jpg"
    assert img.file_name == "test.jpg"
    assert img.file_size == 1024
    assert img.file_mtime == 1700000000.0
    assert img.status == "pending"
    assert img.source_type == "local"
    assert img.phash is None
    assert img.dhash is None
    assert img.ai_description is None


async def test_create_image_full(session: AsyncSession) -> None:
    """An Image with all optional fields can be persisted correctly."""
    now = datetime.datetime(2023, 6, 15, 12, 0, 0)
    img = Image(
        file_path="/photos/full.jpg",
        file_name="full.jpg",
        file_size=2048,
        file_mtime=1700000001.0,
        phash="abc123",
        dhash="def456",
        width=4000,
        height=3000,
        format="JPEG",
        exif_date=now,
        exif_camera_make="Canon",
        exif_camera_model="EOS R5",
        exif_gps_lat=60.1699,
        exif_gps_lon=24.9384,
        exif_focal_length=50.0,
        exif_aperture=1.8,
        exif_iso=400,
        exif_exposure="1/200",
        ai_description="A beautiful landscape",
        ai_tags='["landscape", "nature"]',
        ai_quality_score=0.95,
        ai_model="gpt-4o",
        status="indexed",
        source_type="local",
    )
    session.add(img)
    await session.commit()
    await session.refresh(img)

    assert img.id is not None
    assert img.phash == "abc123"
    assert img.dhash == "def456"
    assert img.width == 4000
    assert img.height == 3000
    assert img.format == "JPEG"
    assert img.exif_camera_make == "Canon"
    assert img.exif_camera_model == "EOS R5"
    assert img.exif_gps_lat == pytest.approx(60.1699)
    assert img.exif_gps_lon == pytest.approx(24.9384)
    assert img.exif_focal_length == pytest.approx(50.0)
    assert img.exif_aperture == pytest.approx(1.8)
    assert img.exif_iso == 400
    assert img.exif_exposure == "1/200"
    assert img.ai_description == "A beautiful landscape"
    assert img.ai_tags == '["landscape", "nature"]'
    assert img.ai_quality_score == pytest.approx(0.95)
    assert img.ai_model == "gpt-4o"
    assert img.status == "indexed"


async def test_image_unique_file_path(session: AsyncSession) -> None:
    """Inserting two Images with the same file_path raises an integrity error."""
    from sqlalchemy.exc import IntegrityError

    img1 = Image(
        file_path="/photos/dup.jpg",
        file_name="dup.jpg",
        file_size=512,
        file_mtime=1700000002.0,
    )
    img2 = Image(
        file_path="/photos/dup.jpg",
        file_name="dup.jpg",
        file_size=512,
        file_mtime=1700000003.0,
    )
    session.add(img1)
    await session.commit()

    session.add(img2)
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_image_status_values(session: AsyncSession) -> None:
    """Images can hold each valid status value."""
    statuses = ["pending", "indexed", "kept", "rejected", "error", "missing"]
    for i, status in enumerate(statuses):
        img = Image(
            file_path=f"/photos/status_{i}.jpg",
            file_name=f"status_{i}.jpg",
            file_size=100,
            file_mtime=float(1700000000 + i),
            status=status,
        )
        session.add(img)
    await session.commit()
    # If we got here without exceptions all status strings are accepted
    assert True


# ---------------------------------------------------------------------------
# DuplicateGroup / DuplicateGroupMember tests
# ---------------------------------------------------------------------------


async def test_duplicate_group_with_members(session: AsyncSession) -> None:
    """A DuplicateGroup with two member images can be created and related."""
    img1 = Image(
        file_path="/photos/a.jpg",
        file_name="a.jpg",
        file_size=1000,
        file_mtime=1700000010.0,
    )
    img2 = Image(
        file_path="/photos/b.jpg",
        file_name="b.jpg",
        file_size=1000,
        file_mtime=1700000011.0,
    )
    session.add_all([img1, img2])
    await session.flush()  # get IDs without committing

    group = DuplicateGroup(match_type="phash")
    session.add(group)
    await session.flush()

    member1 = DuplicateGroupMember(
        group_id=group.id,
        image_id=img1.id,
        is_best=True,
    )
    member2 = DuplicateGroupMember(
        group_id=group.id,
        image_id=img2.id,
        is_best=False,
        user_choice="keep",
    )
    session.add_all([member1, member2])
    await session.commit()

    await session.refresh(group)
    # Lazy-load members via relationship
    await session.refresh(group, ["members"])

    assert len(group.members) == 2
    best_members = [m for m in group.members if m.is_best]
    assert len(best_members) == 1
    assert best_members[0].image_id == img1.id

    non_best = [m for m in group.members if not m.is_best]
    assert non_best[0].user_choice == "keep"


async def test_duplicate_group_member_relationships(session: AsyncSession) -> None:
    """DuplicateGroupMember back-references group and image correctly."""
    img = Image(
        file_path="/photos/c.jpg",
        file_name="c.jpg",
        file_size=500,
        file_mtime=1700000020.0,
    )
    session.add(img)
    await session.flush()

    group = DuplicateGroup(match_type="dhash")
    session.add(group)
    await session.flush()

    member = DuplicateGroupMember(group_id=group.id, image_id=img.id)
    session.add(member)
    await session.commit()
    await session.refresh(member)

    assert member.group_id == group.id
    assert member.image_id == img.id
    assert member.is_best is False
    assert member.user_choice is None


# ---------------------------------------------------------------------------
# Setting tests
# ---------------------------------------------------------------------------


async def test_setting_crud(session: AsyncSession) -> None:
    """Setting can be created, read, updated, and deleted."""
    from sqlalchemy import select

    # Create
    setting = Setting(key="scan_directory", value="/photos")
    session.add(setting)
    await session.commit()

    # Read
    result = await session.execute(
        select(Setting).where(Setting.key == "scan_directory")
    )
    fetched = result.scalar_one()
    assert fetched.value == "/photos"

    # Update
    fetched.value = "/new/photos"
    await session.commit()
    await session.refresh(fetched)
    assert fetched.value == "/new/photos"

    # Delete
    await session.delete(fetched)
    await session.commit()
    result2 = await session.execute(
        select(Setting).where(Setting.key == "scan_directory")
    )
    assert result2.scalar_one_or_none() is None


async def test_setting_primary_key(session: AsyncSession) -> None:
    """Setting key acts as primary key; duplicate keys raise IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    s1 = Setting(key="theme", value="dark")
    s2 = Setting(key="theme", value="light")
    session.add(s1)
    await session.commit()

    session.add(s2)
    with pytest.raises(IntegrityError):
        await session.commit()
