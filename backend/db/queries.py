"""Database query helpers for image search and duplicate resolution."""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import DuplicateGroup, DuplicateGroupMember, Image


async def search_images(
    session: AsyncSession,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    camera: Optional[str] = None,
    min_quality: Optional[float] = None,
    status: Optional[str] = None,
    exclude_statuses: Optional[list[str]] = None,
    folder: Optional[str] = None,
    media: Optional[str] = None,
    time_near: Optional[str] = None,
    time_range: int = 120,
    has_ai: Optional[bool] = None,
    custom_tag: Optional[str] = None,
    include_tagged: bool = False,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: Optional[float] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Image], int]:
    """Search images with optional filters, FTS5, sorting and pagination.

    Parameters
    ----------
    session:    Active async SQLAlchemy session.
    q:          Full-text search query applied against the FTS5 index.
    date_from:  ISO date string; filter exif_date >= this value.
    date_to:    ISO date string; filter exif_date <= this value.
    camera:     Substring match against exif_camera_make or exif_camera_model.
    min_quality: Minimum ai_quality_score (inclusive).
    status:     Exact status to filter by.  When None, rejected/missing/error
                rows are excluded.
    sort:       Column name to sort by (must be a valid Image attribute).
    order:      ``"asc"`` or ``"desc"``.
    page:       1-based page number.
    limit:      Number of rows per page.

    Returns
    -------
    Tuple of (list of Image objects, total count before pagination).
    """
    stmt = select(Image)

    # Status filter
    from sqlalchemy import or_
    if status:
        stmt = stmt.where(Image.status == status)
    elif exclude_statuses:
        all_excludes = set(exclude_statuses) | {"missing", "error"}
        if include_tagged:
            # Show normal images + tagged ones even if rejected
            stmt = stmt.where(or_(
                Image.status.notin_(list(all_excludes)),
                Image.custom_tag.is_not(None),
            ))
        else:
            stmt = stmt.where(Image.status.notin_(list(all_excludes)))
    else:
        stmt = stmt.where(Image.status.notin_(["missing", "error"]))

    # Media type filter
    if media == "video":
        from backend.indexer.scanner import VIDEO_EXTENSIONS
        video_exts = [ext.upper().lstrip(".") for ext in VIDEO_EXTENSIONS]
        stmt = stmt.where(Image.format.in_(video_exts))
    elif media == "photo":
        from backend.indexer.scanner import VIDEO_EXTENSIONS
        video_exts = [ext.upper().lstrip(".") for ext in VIDEO_EXTENSIONS]
        stmt = stmt.where(Image.format.notin_(video_exts))

    # Time proximity filter
    if time_near:
        from datetime import timedelta
        center = datetime.datetime.fromisoformat(time_near)
        delta = timedelta(seconds=time_range)
        stmt = stmt.where(Image.exif_date >= center - delta, Image.exif_date <= center + delta)

    # AI description filter
    if has_ai:
        stmt = stmt.where(Image.ai_description.is_not(None))

    # Custom tag filter
    if custom_tag == "__any__":
        stmt = stmt.where(Image.custom_tag.is_not(None))
    elif custom_tag:
        stmt = stmt.where(Image.custom_tag == custom_tag)

    # GPS proximity filter (bounding box approximation)
    if lat is not None and lon is not None and radius is not None:
        # ~111 km per degree latitude, longitude varies by cos(lat)
        import math
        lat_delta = radius / 111.0
        lon_delta = radius / (111.0 * math.cos(math.radians(lat)))
        stmt = stmt.where(
            Image.exif_gps_lat >= lat - lat_delta,
            Image.exif_gps_lat <= lat + lat_delta,
            Image.exif_gps_lon >= lon - lon_delta,
            Image.exif_gps_lon <= lon + lon_delta,
        )

    # Folder filter (prefix match on file_path)
    if folder:
        stmt = stmt.where(Image.file_path.startswith(folder))

    # Full-text search via FTS5
    if q:
        fts_result = await session.execute(
            text("SELECT rowid FROM images_fts WHERE images_fts MATCH :q"),
            {"q": q},
        )
        matching_ids = [row[0] for row in fts_result.fetchall()]
        stmt = stmt.where(Image.id.in_(matching_ids))

    # Date range filters
    if date_from:
        stmt = stmt.where(Image.exif_date >= datetime.datetime.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Image.exif_date <= datetime.datetime.fromisoformat(date_to))

    # Camera filter (make OR model contains the string)
    if camera:
        stmt = stmt.where(
            Image.exif_camera_make.contains(camera)
            | Image.exif_camera_model.contains(camera)
        )

    # Minimum quality score
    if min_quality is not None:
        stmt = stmt.where(Image.ai_quality_score >= min_quality)

    # Count total matching rows before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await session.execute(count_stmt)).scalar_one()

    # Sorting
    sort_col = getattr(Image, sort, None)
    if sort_col is None:
        sort_col = Image.created_at
    if order == "asc":
        stmt = stmt.order_by(sort_col.asc())
    else:
        stmt = stmt.order_by(sort_col.desc())

    # Pagination
    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    images = list(result.scalars().all())

    return images, total


async def get_duplicate_groups(
    session: AsyncSession,
    pending_only: bool = False,
) -> list[dict]:
    """Fetch all duplicate groups with their member images.

    Parameters
    ----------
    session:      Active async SQLAlchemy session.
    pending_only: When True, only return groups that contain at least one
                  member whose ``user_choice`` is NULL (unresolved).

    Returns
    -------
    List of dicts, each with keys: ``id``, ``match_type``, ``created_at``,
    ``members`` (list of dicts with ``image_id``, ``is_best``,
    ``user_choice``, ``image``).
    """
    group_stmt = select(DuplicateGroup)
    result = await session.execute(group_stmt)
    groups = list(result.scalars().all())

    output: list[dict] = []
    for group in groups:
        # Fetch members for this group, eagerly joining the Image
        member_stmt = (
            select(DuplicateGroupMember)
            .where(DuplicateGroupMember.group_id == group.id)
        )
        member_result = await session.execute(member_stmt)
        members = list(member_result.scalars().all())

        if pending_only:
            has_unresolved = any(m.user_choice is None for m in members)
            if not has_unresolved:
                continue

        member_dicts: list[dict] = []
        for member in members:
            # Eagerly load the related Image
            image_stmt = select(Image).where(Image.id == member.image_id)
            image_result = await session.execute(image_stmt)
            image = image_result.scalar_one_or_none()

            member_dicts.append(
                {
                    "image_id": member.image_id,
                    "is_best": member.is_best,
                    "user_choice": member.user_choice,
                    "image": image,
                }
            )

        output.append(
            {
                "id": group.id,
                "match_type": group.match_type,
                "created_at": group.created_at,
                "members": member_dicts,
            }
        )

    return output


async def resolve_duplicate_group(
    session: AsyncSession,
    group_id: int,
    keep_ids: list[int],
    reject_ids: list[int],
) -> None:
    """Resolve a duplicate group by setting user choices on members and images.

    For each image_id in ``keep_ids``:   member.user_choice = "keep",   image.status = "kept".
    For each image_id in ``reject_ids``: member.user_choice = "reject", image.status = "rejected".

    Parameters
    ----------
    session:    Active async SQLAlchemy session.
    group_id:   Primary key of the DuplicateGroup to resolve.
    keep_ids:   List of image IDs to mark as kept.
    reject_ids: List of image IDs to mark as rejected.
    """
    all_ids = list(keep_ids) + list(reject_ids)

    member_stmt = select(DuplicateGroupMember).where(
        DuplicateGroupMember.group_id == group_id,
        DuplicateGroupMember.image_id.in_(all_ids),
    )
    member_result = await session.execute(member_stmt)
    members = list(member_result.scalars().all())

    image_stmt = select(Image).where(Image.id.in_(all_ids))
    image_result = await session.execute(image_stmt)
    images = {img.id: img for img in image_result.scalars().all()}

    _now = datetime.datetime.utcnow()
    for member in members:
        if member.image_id in keep_ids:
            member.user_choice = "keep"
            if member.image_id in images:
                images[member.image_id].status = "kept"
                images[member.image_id].status_changed_at = _now
        elif member.image_id in reject_ids:
            member.user_choice = "reject"
            if member.image_id in images:
                images[member.image_id].status = "rejected"
                images[member.image_id].status_changed_at = _now

    await session.commit()
