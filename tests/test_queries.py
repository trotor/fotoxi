"""Tests for backend/db/queries.py (Task 12)."""
from __future__ import annotations

import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import DuplicateGroup, DuplicateGroupMember, Image
from backend.db.queries import (
    bulk_resolve_duplicates,
    get_duplicate_groups,
    resolve_duplicate_group,
    search_images,
)
from backend.db.session import create_engine_and_init


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """Fresh in-memory database with ORM tables and FTS5 virtual table."""
    engine, factory = await create_engine_and_init(":memory:")
    yield engine, factory
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db):
    """AsyncSession bound to the in-memory database."""
    engine, factory = db
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_image(
    session: AsyncSession,
    *,
    file_path: str,
    file_name: str,
    ai_description: str = "",
    ai_tags: str = "",
    exif_date: datetime.datetime | None = None,
    exif_camera_make: str | None = None,
    exif_camera_model: str | None = None,
    ai_quality_score: float | None = None,
    status: str = "indexed",
) -> Image:
    """Insert an Image and sync it into the FTS5 index."""
    img = Image(
        file_path=file_path,
        file_name=file_name,
        file_size=1024,
        file_mtime=1700000000.0,
        ai_description=ai_description or None,
        ai_tags=ai_tags or None,
        exif_date=exif_date,
        exif_camera_make=exif_camera_make,
        exif_camera_model=exif_camera_model,
        ai_quality_score=ai_quality_score,
        status=status,
    )
    session.add(img)
    await session.flush()

    # Populate FTS index
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


# ---------------------------------------------------------------------------
# search_images tests
# ---------------------------------------------------------------------------


async def test_search_text(session: AsyncSession) -> None:
    """FTS search returns only the image whose description matches the keyword."""
    img_cat = await _make_image(
        session,
        file_path="/photos/cat.jpg",
        file_name="cat.jpg",
        ai_description="A fluffy orange cat sitting on a windowsill",
    )
    await _make_image(
        session,
        file_path="/photos/dog.jpg",
        file_name="dog.jpg",
        ai_description="A golden retriever running in the park",
    )

    results, total = await search_images(session, q="fluffy")

    assert total == 1
    assert len(results) == 1
    assert results[0].id == img_cat.id


async def test_search_date_filter(session: AsyncSession) -> None:
    """date_from filter excludes images with exif_date before the boundary."""
    early = datetime.datetime(2020, 1, 1, 12, 0, 0)
    late = datetime.datetime(2023, 6, 15, 12, 0, 0)

    await _make_image(
        session,
        file_path="/photos/early.jpg",
        file_name="early.jpg",
        exif_date=early,
    )
    img_late = await _make_image(
        session,
        file_path="/photos/late.jpg",
        file_name="late.jpg",
        exif_date=late,
    )

    results, total = await search_images(session, date_from="2022-01-01")

    assert total == 1
    assert len(results) == 1
    assert results[0].id == img_late.id


async def test_search_camera_filter(session: AsyncSession) -> None:
    """camera filter matches images whose make or model contains the string."""
    img_canon = await _make_image(
        session,
        file_path="/photos/canon.jpg",
        file_name="canon.jpg",
        exif_camera_make="Canon",
        exif_camera_model="EOS R5",
    )
    await _make_image(
        session,
        file_path="/photos/nikon.jpg",
        file_name="nikon.jpg",
        exif_camera_make="Nikon",
        exif_camera_model="D850",
    )

    results, total = await search_images(session, camera="Canon")

    assert total == 1
    assert len(results) == 1
    assert results[0].id == img_canon.id


async def test_search_pagination(session: AsyncSession) -> None:
    """With limit=1, total reflects full count while only one result is returned."""
    await _make_image(
        session,
        file_path="/photos/img1.jpg",
        file_name="img1.jpg",
    )
    await _make_image(
        session,
        file_path="/photos/img2.jpg",
        file_name="img2.jpg",
    )

    results, total = await search_images(session, limit=1, page=1)

    assert total == 2
    assert len(results) == 1


async def test_search_excludes_rejected_by_default(session: AsyncSession) -> None:
    """Without an explicit status filter, rejected/missing/error images are excluded."""
    await _make_image(
        session,
        file_path="/photos/good.jpg",
        file_name="good.jpg",
        status="indexed",
    )
    await _make_image(
        session,
        file_path="/photos/bad.jpg",
        file_name="bad.jpg",
        status="rejected",
    )

    results, total = await search_images(session, exclude_statuses=["rejected", "pending"])

    assert total == 1
    assert all(r.status not in ("rejected", "missing", "error") for r in results)


async def test_search_explicit_status_filter(session: AsyncSession) -> None:
    """Providing status='rejected' returns only rejected images."""
    await _make_image(
        session,
        file_path="/photos/good2.jpg",
        file_name="good2.jpg",
        status="indexed",
    )
    img_rej = await _make_image(
        session,
        file_path="/photos/bad2.jpg",
        file_name="bad2.jpg",
        status="rejected",
    )

    results, total = await search_images(session, status="rejected")

    assert total == 1
    assert results[0].id == img_rej.id


# ---------------------------------------------------------------------------
# get_duplicate_groups tests
# ---------------------------------------------------------------------------


async def _make_dup_group(
    session: AsyncSession,
    *,
    match_type: str = "phash",
    image_statuses: list[str] | None = None,
    user_choices: list[str | None] | None = None,
) -> tuple[DuplicateGroup, list[Image]]:
    """Create a DuplicateGroup with two member images and return them."""
    statuses = image_statuses or ["indexed", "indexed"]
    choices = user_choices or [None, None]

    images: list[Image] = []
    for i, st in enumerate(statuses):
        img = Image(
            file_path=f"/photos/dup_{match_type}_{i}.jpg",
            file_name=f"dup_{match_type}_{i}.jpg",
            file_size=512,
            file_mtime=float(1700000000 + i),
            status=st,
        )
        session.add(img)
        images.append(img)
    await session.flush()

    group = DuplicateGroup(match_type=match_type)
    session.add(group)
    await session.flush()

    for idx, (img, choice) in enumerate(zip(images, choices)):
        member = DuplicateGroupMember(
            group_id=group.id,
            image_id=img.id,
            is_best=(idx == 0),
            user_choice=choice,
        )
        session.add(member)

    await session.commit()
    return group, images


async def test_get_duplicate_groups_returns_all(session: AsyncSession) -> None:
    """get_duplicate_groups returns all groups with member data."""
    group, images = await _make_dup_group(session, match_type="phash")

    groups = await get_duplicate_groups(session)

    assert len(groups) == 1
    g = groups[0]
    assert g["id"] == group.id
    assert g["match_type"] == "phash"
    assert len(g["members"]) == 2
    assert all("image" in m for m in g["members"])


async def test_get_duplicate_groups_pending_only(session: AsyncSession) -> None:
    """pending_only=True excludes groups where all members have a user_choice."""
    # Group with unresolved members
    await _make_dup_group(session, match_type="phash", user_choices=[None, None])
    # Group already fully resolved
    await _make_dup_group(session, match_type="dhash", user_choices=["keep", "reject"])

    groups = await get_duplicate_groups(session, pending_only=True)

    assert len(groups) == 1
    assert groups[0]["match_type"] == "phash"


# ---------------------------------------------------------------------------
# resolve_duplicate_group tests
# ---------------------------------------------------------------------------


async def test_resolve_duplicate_group(session: AsyncSession) -> None:
    """resolve_duplicate_group sets member choices and image statuses correctly."""
    group, images = await _make_dup_group(session, match_type="phash")
    keep_img, reject_img = images

    await resolve_duplicate_group(
        session,
        group_id=group.id,
        keep_ids=[keep_img.id],
        reject_ids=[reject_img.id],
    )

    await session.refresh(keep_img)
    await session.refresh(reject_img)

    assert keep_img.status == "kept"
    assert reject_img.status == "rejected"

    # Check member choices
    from sqlalchemy import select

    members_result = await session.execute(
        select(DuplicateGroupMember).where(
            DuplicateGroupMember.group_id == group.id
        )
    )
    members = list(members_result.scalars().all())
    choices = {m.image_id: m.user_choice for m in members}

    assert choices[keep_img.id] == "keep"
    assert choices[reject_img.id] == "reject"


# ---------------------------------------------------------------------------
# bulk_resolve_duplicates tests
# ---------------------------------------------------------------------------


async def _make_varied_group(
    session: AsyncSession,
    *,
    match_type: str,
    specs: list[dict],
    user_choices: list[str | None] | None = None,
) -> tuple[DuplicateGroup, list[Image]]:
    """Create a DuplicateGroup whose members differ in resolution/size/path."""
    images: list[Image] = []
    for i, s in enumerate(specs):
        img = Image(
            file_path=s.get("file_path", f"/photos/{match_type}_{i}.jpg"),
            file_name=f"{match_type}_{i}.jpg",
            file_size=s.get("file_size", 100),
            file_mtime=float(1700000000 + i),
            width=s.get("width"),
            height=s.get("height"),
            status=s.get("status", "indexed"),
        )
        session.add(img)
        images.append(img)
    await session.flush()

    group = DuplicateGroup(match_type=match_type)
    session.add(group)
    await session.flush()

    choices = user_choices or [None] * len(specs)
    for idx, (img, choice) in enumerate(zip(images, choices)):
        session.add(
            DuplicateGroupMember(
                group_id=group.id,
                image_id=img.id,
                is_best=(idx == 0),
                user_choice=choice,
            )
        )
    await session.commit()
    return group, images


async def test_bulk_resolve_keeps_best_and_rejects_rest(session: AsyncSession) -> None:
    """A copy group is resolved: highest-resolution image kept, the rest rejected."""
    group, images = await _make_varied_group(
        session,
        match_type="exact",
        specs=[
            {"width": 1000, "height": 1000, "file_size": 100},
            {"width": 2000, "height": 2000, "file_size": 100},  # best (resolution)
        ],
    )
    small, big = images

    summary = await bulk_resolve_duplicates(session)

    assert summary["groups"] == 1
    assert summary["kept"] == 1
    assert summary["rejected"] == 1
    assert summary["applied"] is True

    await session.refresh(small)
    await session.refresh(big)
    assert big.status == "kept"
    assert small.status == "rejected"


async def test_bulk_resolve_skips_burst_by_default(session: AsyncSession) -> None:
    """Burst groups are never auto-resolved by default (exclude_burst=True)."""
    _group, images = await _make_varied_group(
        session,
        match_type="burst",
        specs=[
            {"width": 1000, "height": 1000},
            {"width": 1000, "height": 1000},
        ],
    )

    summary = await bulk_resolve_duplicates(session)

    assert summary["groups"] == 0
    for img in images:
        await session.refresh(img)
        assert img.status == "indexed"


async def test_bulk_resolve_dry_run_reports_without_applying(session: AsyncSession) -> None:
    """dry_run reports the summary but changes no statuses or choices."""
    _group, images = await _make_varied_group(
        session,
        match_type="phash",
        specs=[
            {"width": 1000, "height": 1000, "file_size": 100},
            {"width": 2000, "height": 2000, "file_size": 100},
        ],
    )

    summary = await bulk_resolve_duplicates(session, dry_run=True)

    assert summary["groups"] == 1
    assert summary["applied"] is False
    for img in images:
        await session.refresh(img)
        assert img.status == "indexed"


async def test_bulk_resolve_reports_reclaimable_bytes(session: AsyncSession) -> None:
    """reclaimable_bytes sums the file sizes of images that would be rejected."""
    await _make_varied_group(
        session,
        match_type="exact",
        specs=[
            {"width": 2000, "height": 2000, "file_size": 100},  # best (kept)
            {"width": 1000, "height": 1000, "file_size": 300},  # rejected
        ],
    )

    summary = await bulk_resolve_duplicates(session, dry_run=True)

    assert summary["reclaimable_bytes"] == 300


async def test_bulk_resolve_skips_already_resolved(session: AsyncSession) -> None:
    """Groups with any member already chosen are treated as resolved and skipped."""
    await _make_varied_group(
        session,
        match_type="exact",
        specs=[
            {"width": 2000, "height": 2000},
            {"width": 1000, "height": 1000},
        ],
        user_choices=["keep", None],
    )

    summary = await bulk_resolve_duplicates(session)
    assert summary["groups"] == 0


async def test_bulk_resolve_match_types_filter(session: AsyncSession) -> None:
    """match_types restricts resolution to the given exact match_type strings."""
    await _make_varied_group(
        session,
        match_type="exact",
        specs=[{"width": 2000, "height": 2000}, {"width": 1000, "height": 1000}],
    )
    phash_group, phash_images = await _make_varied_group(
        session,
        match_type="phash",
        specs=[{"width": 2000, "height": 2000}, {"width": 1000, "height": 1000}],
    )

    summary = await bulk_resolve_duplicates(session, match_types=["exact"])

    assert summary["groups"] == 1
    # phash group untouched
    for img in phash_images:
        await session.refresh(img)
        assert img.status == "indexed"
