"""REST API routes for Fotoxi."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.db.queries import (
    bulk_resolve_duplicates,
    errors_summary,
    resolve_duplicate_group,
    retry_errored,
    search_images,
    unresolve_duplicate_group,
)
from sqlalchemy import select

from backend.db.models import Image

router = APIRouter()


def _image_to_dict(img: Image) -> Dict[str, Any]:
    """Convert an Image ORM model to a serializable dict."""
    ai_tags = None
    if img.ai_tags is not None:
        try:
            ai_tags = json.loads(img.ai_tags)
        except (json.JSONDecodeError, TypeError):
            ai_tags = img.ai_tags

    return {
        "id": img.id,
        "file_path": img.file_path,
        "file_name": img.file_name,
        "file_size": img.file_size,
        "file_mtime": img.file_mtime,
        "source_type": img.source_type,
        "phash": img.phash,
        "dhash": img.dhash,
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "exif_date": img.exif_date.isoformat() if img.exif_date is not None else None,
        "exif_camera_make": img.exif_camera_make,
        "exif_camera_model": img.exif_camera_model,
        "exif_gps_lat": img.exif_gps_lat,
        "exif_gps_lon": img.exif_gps_lon,
        "gps_inherited": img.gps_inherited,
        "location_name": img.location_name,
        "exif_focal_length": img.exif_focal_length,
        "exif_aperture": img.exif_aperture,
        "exif_iso": img.exif_iso,
        "exif_exposure": img.exif_exposure,
        "ai_description": img.ai_description,
        "ai_tags": ai_tags,
        "ai_quality_score": img.ai_quality_score,
        "ai_model": img.ai_model,
        "status": img.status,
        "custom_tag": img.custom_tag,
        "rotation": img.rotation,
        "error_message": img.error_message,
        "indexed_at": img.indexed_at.isoformat() if img.indexed_at is not None else None,
        "status_changed_at": img.status_changed_at.isoformat() if img.status_changed_at is not None else None,
        "rejected_at": img.rejected_at.isoformat() if img.rejected_at is not None else None,
        "kept_at": img.kept_at.isoformat() if img.kept_at is not None else None,
        "tagged_at": img.tagged_at.isoformat() if img.tagged_at is not None else None,
        "created_at": img.created_at.isoformat() if img.created_at is not None else None,
        "updated_at": img.updated_at.isoformat() if img.updated_at is not None else None,
    }


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


@router.post("/images/refresh-videos")
async def refresh_video_metadata(request: Request) -> Dict[str, Any]:
    """Re-extract metadata for all video files (fixes incorrect dates)."""
    from sqlalchemy import select as sa_select
    from backend.indexer.exif import extract_exif
    from backend.indexer.scanner import VIDEO_EXTENSIONS

    video_exts_upper = [ext.upper().lstrip(".") for ext in VIDEO_EXTENSIONS]
    session_factory = request.app.state.session_factory

    updated = 0
    errors = 0
    loop = asyncio.get_event_loop()

    async with session_factory() as session:
        result = await session.execute(
            sa_select(Image).where(Image.format.in_(video_exts_upper))
        )
        videos = result.scalars().all()

        for img in videos:
            try:
                exif_data = await loop.run_in_executor(
                    None, extract_exif, Path(img.file_path)
                )
                if exif_data and exif_data.get("exif_date"):
                    for key, value in exif_data.items():
                        if hasattr(img, key):
                            setattr(img, key, value)
                    updated += 1
            except Exception:
                errors += 1

        await session.commit()

    return {"updated": updated, "errors": errors, "total": len(videos)}


@router.get("/images")
async def list_images(
    request: Request,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    camera: Optional[str] = None,
    min_quality: Optional[float] = None,
    status: Optional[str] = None,
    exclude: Optional[str] = None,
    folder: Optional[str] = None,
    media: Optional[str] = None,
    time_near: Optional[str] = None,
    time_range: int = 120,
    has_ai: Optional[bool] = None,
    custom_tag: Optional[str] = None,
    only_tagged: Optional[bool] = None,
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: Optional[float] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    session_factory = request.app.state.session_factory
    exclude_list = [s.strip() for s in exclude.split(",")] if exclude else None
    async with session_factory() as session:
        images, total = await search_images(
            session=session,
            q=q,
            date_from=date_from,
            date_to=date_to,
            camera=camera,
            min_quality=min_quality,
            status=status,
            exclude_statuses=exclude_list,
            folder=folder,
            media=media,
            time_near=time_near,
            time_range=time_range,
            has_ai=has_ai,
            custom_tag=custom_tag,
            only_tagged=bool(only_tagged),
            location=location,
            lat=lat,
            lon=lon,
            radius=radius,
            sort=sort,
            order=order,
            page=page,
            limit=limit,
        )
    return {
        "images": [_image_to_dict(img) for img in images],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/images/{image_id}")
async def get_image(request: Request, image_id: int) -> Dict[str, Any]:
    from sqlalchemy import select
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return _image_to_dict(img)


@router.get("/images/{image_id}/thumb")
async def get_image_thumb(request: Request, image_id: int) -> FileResponse:
    config = request.app.state.config
    thumb_path = Path(config.thumbs_dir) / f"{image_id}.jpg"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.get("/images/{image_id}/full")
async def get_image_full(request: Request, image_id: int):
    from sqlalchemy import select
    from fastapi.responses import StreamingResponse
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")
    file_path = Path(img.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    import mimetypes
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    rotation = img.rotation
    # For images needing EXIF fix or manual rotation, process with Pillow
    if media_type.startswith("image/"):
        try:
            from PIL import Image as PILImage
            import io
            pil_img = PILImage.open(file_path)
            needs_stream = False

            # Strip stale EXIF orientation
            orientation = pil_img.getexif().get(274)
            if orientation in (5, 6, 7, 8):
                w, h = pil_img.size
                is_portrait = h > w
                if (is_portrait and orientation in (6, 8)) or (not is_portrait and orientation in (5, 7)):
                    exif = pil_img.getexif()
                    exif[274] = 1  # Normal orientation
                    needs_stream = True

            # Apply manual rotation
            if rotation:
                from PIL import ImageOps
                pil_img = ImageOps.exif_transpose(pil_img)
                pil_img = pil_img.rotate(-rotation, expand=True)
                needs_stream = True

            if needs_stream:
                buf = io.BytesIO()
                save_format = pil_img.format or "JPEG"
                pil_img.save(buf, format=save_format, quality=92)
                buf.seek(0)
                pil_img.close()
                return StreamingResponse(buf, media_type=media_type)
            pil_img.close()
        except Exception:
            pass  # Fall through to normal FileResponse

    return FileResponse(str(file_path), media_type=media_type)


@router.get("/folders")
async def list_image_folders(request: Request) -> List[Dict[str, Any]]:
    """List all unique parent folders that contain images, with total and indexed counts."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(
            select(Image.file_path, Image.status).where(Image.status.notin_(["missing", "error"]))
        )
        rows = result.all()

    # Build folder tree with total and indexed counts
    folder_total: dict[str, int] = {}
    folder_indexed: dict[str, int] = {}
    for path, status in rows:
        parent = str(Path(path).parent)
        folder_total[parent] = folder_total.get(parent, 0) + 1
        if status in ("indexed", "kept"):
            folder_indexed[parent] = folder_indexed.get(parent, 0) + 1

    # Aggregate into parent folders
    agg_total: dict[str, int] = {}
    agg_indexed: dict[str, int] = {}
    for folder, count in folder_total.items():
        parts = folder.split("/")
        for depth in range(1, len(parts) + 1):
            ancestor = "/".join(parts[:depth])
            agg_total[ancestor] = agg_total.get(ancestor, 0) + count
            agg_indexed[ancestor] = agg_indexed.get(ancestor, 0) + folder_indexed.get(folder, 0)

    home = str(Path.home())
    result_list = []
    for folder, count in sorted(agg_total.items()):
        if not folder.startswith(home):
            continue
        depth = len(folder.split("/")) - len(home.split("/"))
        if depth < 1:
            continue
        short = folder.replace(home, "~")
        indexed = agg_indexed.get(folder, 0)
        result_list.append({
            "path": folder, "short": short,
            "count": count, "indexed": indexed,
            "depth": depth,
        })

    return result_list


@router.get("/stats")
async def get_stats(request: Request) -> Dict[str, Any]:
    """Comprehensive statistics about the image database."""
    from sqlalchemy import select, func
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        # Status counts
        status_result = await session.execute(
            select(Image.status, func.count(Image.id)).group_by(Image.status)
        )
        status_counts = dict(status_result.all())

        # GPS stats
        gps_result = await session.execute(
            select(func.count(Image.id)).where(Image.exif_gps_lat.is_not(None))
        )
        gps_count = gps_result.scalar() or 0

        # Date range
        date_result = await session.execute(
            select(func.min(Image.exif_date), func.max(Image.exif_date)).where(Image.exif_date.is_not(None))
        )
        date_row = date_result.one()

        # Camera breakdown (top 10)
        camera_result = await session.execute(
            select(Image.exif_camera_model, func.count(Image.id))
            .where(Image.exif_camera_model.is_not(None), Image.status.notin_(["missing", "error"]))
            .group_by(Image.exif_camera_model)
            .order_by(func.count(Image.id).desc())
            .limit(50)
        )
        cameras = [{"model": r[0], "count": r[1]} for r in camera_result.all()]

        # Total file size
        size_result = await session.execute(
            select(func.sum(Image.file_size)).where(Image.status.notin_(["missing", "error"]))
        )
        total_size = size_result.scalar() or 0

        # Year breakdown
        year_result = await session.execute(
            select(
                func.strftime("%Y", Image.exif_date),
                func.count(Image.id),
            )
            .where(Image.exif_date.is_not(None), Image.status.notin_(["missing", "error"]))
            .group_by(func.strftime("%Y", Image.exif_date))
            .order_by(func.strftime("%Y", Image.exif_date))
        )
        years = [{"year": r[0], "count": r[1]} for r in year_result.all() if r[0]]

        # Month breakdown (year-month)
        month_result = await session.execute(
            select(
                func.strftime("%Y-%m", Image.exif_date),
                func.count(Image.id),
            )
            .where(Image.exif_date.is_not(None), Image.status.notin_(["missing", "error"]))
            .group_by(func.strftime("%Y-%m", Image.exif_date))
            .order_by(func.strftime("%Y-%m", Image.exif_date))
        )
        months = [{"month": r[0], "count": r[1]} for r in month_result.all() if r[0]]

        # Duplicate stats
        from backend.db.models import DuplicateGroup, DuplicateGroupMember
        dup_result = await session.execute(select(func.count(DuplicateGroup.id)))
        dup_groups = dup_result.scalar() or 0
        dup_members_result = await session.execute(select(func.count(DuplicateGroupMember.id)))
        dup_members = dup_members_result.scalar() or 0

    return {
        "status_counts": status_counts,
        "total": sum(status_counts.values()),
        "gps_count": gps_count,
        "date_min": date_row[0].isoformat() if date_row[0] else None,
        "date_max": date_row[1].isoformat() if date_row[1] else None,
        "cameras": cameras,
        "total_size_bytes": total_size,
        "years": years,
        "duplicate_groups": dup_groups,
        "duplicate_images": dup_members,
        "months": months,
    }


class FolderExcludeRequest(BaseModel):
    path: str


@router.post("/folders/exclude")
async def exclude_folder(request: Request, body: FolderExcludeRequest) -> Dict[str, Any]:
    """Exclude a folder: add its name to exclude_patterns and reject its images."""
    config = request.app.state.config
    session_factory = request.app.state.session_factory

    folder_name = Path(body.path).name
    if folder_name not in config.exclude_patterns:
        config.exclude_patterns.append(folder_name)

    # Reject all images in this folder
    async with session_factory() as session:
        result = await session.execute(
            select(Image).where(
                Image.file_path.startswith(body.path),
                Image.status.notin_(["rejected", "missing"]),
            )
        )
        images = result.scalars().all()
        count = 0
        for img in images:
            img.status = "rejected"
            count += 1
        await session.commit()

    # Persist exclude_patterns
    import json as _json
    from backend.db.models import Setting
    async with session_factory() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "exclude_patterns")
        )
        existing = result.scalar_one_or_none()
        val = _json.dumps(config.exclude_patterns)
        if existing:
            existing.value = val
        else:
            session.add(Setting(key="exclude_patterns", value=val))
        await session.commit()

    return {"excluded": folder_name, "rejected_count": count}


class ImageStatusUpdate(BaseModel):
    status: str  # "rejected", "indexed", "kept"


@router.patch("/images/{image_id}/status")
async def update_image_status(request: Request, image_id: int, body: ImageStatusUpdate) -> Dict[str, Any]:
    """Update an image's status (reject, restore, keep)."""
    from sqlalchemy import select as sa_select
    allowed = {"rejected", "indexed", "kept"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {allowed}")
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(sa_select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")
        import datetime
        now = datetime.datetime.utcnow()
        img.status = body.status
        img.status_changed_at = now
        if body.status == 'kept':
            img.kept_at = now
        elif body.status == 'rejected':
            img.rejected_at = now
        elif body.status == 'indexed':
            # Clearing status — reset specific timestamps
            img.kept_at = None
            img.rejected_at = None
        await session.commit()
    return {"id": image_id, "status": body.status}


class ImageTagUpdate(BaseModel):
    custom_tag: Optional[str] = None


@router.patch("/images/{image_id}/tag")
async def update_image_tag(request: Request, image_id: int, body: ImageTagUpdate) -> Dict[str, Any]:
    """Set or clear custom_tag on an image. Setting a tag also rejects the image."""
    from sqlalchemy import select as sa_select
    import datetime

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(sa_select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")
        now = datetime.datetime.utcnow()
        img.custom_tag = body.custom_tag
        img.status_changed_at = now
        img.tagged_at = now if body.custom_tag else None
        await session.commit()
    return {"id": image_id, "custom_tag": body.custom_tag, "status": img.status}


@router.patch("/images/{image_id}/rotate")
async def rotate_image(image_id: int, request: Request) -> Dict[str, Any]:
    """Rotate image 90° clockwise and regenerate thumbnail."""
    from sqlalchemy import select as sa_select
    from backend.indexer.thumbnailer import generate_thumbnail
    from pathlib import Path

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(sa_select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")
        img.rotation = (img.rotation + 90) % 360
        rotation = img.rotation
        file_path = img.file_path
        await session.commit()

    # Regenerate thumbnail with rotation applied
    thumbs_dir = Path("data/thumbs")
    source = Path(file_path)
    if source.exists():
        generate_thumbnail(source, thumbs_dir, image_id, rotation=rotation)

    return {"id": image_id, "rotation": rotation}


@router.post("/images/bulk-reject-missing")
async def bulk_reject_missing(request: Request) -> Dict[str, Any]:
    """Reject all images with status 'missing'."""
    from sqlalchemy import select as sa_select, update as sa_update
    import datetime

    now = datetime.datetime.utcnow()
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(
            sa_select(Image).where(Image.status == "missing")
        )
        missing = result.scalars().all()
        count = len(missing)
        for img in missing:
            img.status = "rejected"
            img.status_changed_at = now
            img.rejected_at = now
        await session.commit()
    return {"rejected_count": count}


@router.post("/images/{image_id}/reveal")
async def reveal_image_in_finder(request: Request, image_id: int) -> Dict[str, Any]:
    """Open the image's parent folder in Finder with the file selected."""
    from sqlalchemy import select as sa_select
    import subprocess

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(sa_select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")

    file_path = Path(img.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    subprocess.Popen(["open", "-R", str(file_path)])
    return {"id": image_id, "revealed": True}


@router.post("/images/{image_id}/refresh-metadata")
async def refresh_image_metadata(request: Request, image_id: int) -> Dict[str, Any]:
    """Re-extract metadata (EXIF/video) for a single image from its source file."""
    from sqlalchemy import select as sa_select
    from backend.indexer.exif import extract_exif

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(sa_select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")

        path = Path(img.file_path)
        loop = asyncio.get_event_loop()
        exif_data = await loop.run_in_executor(None, extract_exif, path)
        if exif_data is None:
            raise HTTPException(status_code=422, detail="Cannot read file metadata")

        import datetime
        for key, value in exif_data.items():
            if hasattr(img, key):
                setattr(img, key, value)
        img.updated_at = datetime.datetime.utcnow()
        await session.commit()

    return {"id": image_id, "refreshed": True}


# In-progress single-image refresh tasks
_refresh_tasks: Dict[int, str] = {}  # image_id -> status ("metadata"|"thumbnail"|"ai"|"done"|"error")


@router.post("/images/{image_id}/refresh-all")
async def refresh_image_all(request: Request, image_id: int) -> Dict[str, Any]:
    """Full refresh: metadata + thumbnail + AI analysis. AI runs in background."""
    from sqlalchemy import select as sa_select
    from backend.indexer.exif import extract_exif
    from backend.indexer.thumbnailer import generate_thumbnail
    from backend.indexer.analyzer import analyze_image
    import datetime

    session_factory = request.app.state.session_factory
    config = request.app.state.config

    # Get image
    async with session_factory() as session:
        result = await session.execute(sa_select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")
        file_path = img.file_path
        file_name = img.file_name

    loop = asyncio.get_event_loop()
    _refresh_tasks[image_id] = "metadata"

    async def _do_refresh():
        try:
            # 1. Metadata
            _refresh_tasks[image_id] = "metadata"
            exif_data = await loop.run_in_executor(None, extract_exif, Path(file_path))
            if exif_data:
                async with session_factory() as session:
                    result = await session.execute(sa_select(Image).where(Image.id == image_id))
                    img = result.scalar_one_or_none()
                    if img:
                        for key, value in exif_data.items():
                            if hasattr(img, key):
                                setattr(img, key, value)
                        img.updated_at = datetime.datetime.utcnow()
                        await session.commit()

            # 2. Thumbnail
            _refresh_tasks[image_id] = "thumbnail"
            await loop.run_in_executor(
                None, generate_thumbnail, Path(file_path), Path(config.thumbs_dir), image_id
            )

            # 3. AI analysis
            _refresh_tasks[image_id] = "ai"
            thumb_path = Path(config.thumbs_dir) / f"{image_id}.jpg"
            ai_result = await loop.run_in_executor(
                None,
                lambda: analyze_image(
                    path=file_path,
                    ollama_url=config.ollama_url,
                    model=config.ollama_model,
                    language=config.ai_language,
                    quality_enabled=config.ai_quality_enabled,
                    thumb_path=thumb_path,
                ),
            )
            if ai_result:
                async with session_factory() as session:
                    result = await session.execute(sa_select(Image).where(Image.id == image_id))
                    img = result.scalar_one_or_none()
                    if img:
                        import json as _json
                        desc = ai_result.get("description", "")
                        tags = ai_result.get("tags", [])
                        tags_json = _json.dumps(tags) if tags else None
                        lang = config.ai_language
                        img.ai_description = desc
                        img.ai_tags = tags_json
                        if lang in ("english", "en"):
                            img.ai_description_en = desc
                            img.ai_tags_en = tags_json
                        elif lang in ("finnish", "fi"):
                            img.ai_description_fi = desc
                            img.ai_tags_fi = tags_json
                        img.ai_quality_score = ai_result.get("quality_score")
                        img.ai_model = config.ollama_model
                        img.indexed_at = datetime.datetime.utcnow()
                        img.updated_at = datetime.datetime.utcnow()
                        await session.commit()

            _refresh_tasks[image_id] = "done"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("refresh-all error for %s: %s", file_name, exc)
            _refresh_tasks[image_id] = "error"

    asyncio.create_task(_do_refresh())
    return {"id": image_id, "status": "started"}


@router.get("/images/{image_id}/refresh-status")
async def refresh_image_status(request: Request, image_id: int) -> Dict[str, Any]:
    """Check the progress of a single-image refresh-all operation."""
    status = _refresh_tasks.get(image_id)
    return {"id": image_id, "refresh_status": status}


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


@router.get("/duplicates")
async def list_duplicates(
    request: Request,
    status: Optional[str] = None,
    match_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """List duplicate groups with pagination. Only unresolved groups by default."""
    from sqlalchemy import select as sa_select, func
    from backend.db.models import DuplicateGroup, DuplicateGroupMember

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        # Find unresolved group IDs efficiently (single query)
        resolved_subq = (
            sa_select(DuplicateGroupMember.group_id)
            .where(DuplicateGroupMember.user_choice.is_not(None))
            .distinct()
            .subquery()
        )
        unresolved_q = (
            sa_select(DuplicateGroup.id)
            .where(DuplicateGroup.id.notin_(sa_select(resolved_subq.c.group_id)))
        )

        # Filter by match_type if specified
        if match_type:
            unresolved_q = unresolved_q.where(DuplicateGroup.match_type.contains(match_type))

        # Count total
        count_result = await session.execute(
            sa_select(func.count()).select_from(unresolved_q.subquery())
        )
        total = count_result.scalar() or 0

        # Paginated group IDs
        page_q = unresolved_q.order_by(DuplicateGroup.id).offset((page - 1) * limit).limit(limit)
        group_ids_result = await session.execute(page_q)
        group_ids = [r[0] for r in group_ids_result.all()]

        if not group_ids:
            return {"groups": [], "total": total, "page": page, "limit": limit}

        # Fetch groups
        groups_result = await session.execute(
            sa_select(DuplicateGroup).where(DuplicateGroup.id.in_(group_ids)).order_by(DuplicateGroup.id)
        )
        groups = {g.id: g for g in groups_result.scalars().all()}

        # Fetch ALL members for these groups in ONE query
        members_result = await session.execute(
            sa_select(DuplicateGroupMember).where(DuplicateGroupMember.group_id.in_(group_ids))
        )
        all_members = list(members_result.scalars().all())

        # Fetch ALL images for these members in ONE query
        image_ids = [m.image_id for m in all_members]
        images_result = await session.execute(
            sa_select(Image).where(Image.id.in_(image_ids))
        )
        images_map = {img.id: img for img in images_result.scalars().all()}

    # Build response
    result = []
    members_by_group: dict[int, list] = {}
    for m in all_members:
        members_by_group.setdefault(m.group_id, []).append(m)

    for gid in group_ids:
        g = groups.get(gid)
        if not g:
            continue
        members = []
        for m in members_by_group.get(gid, []):
            img = images_map.get(m.image_id)
            members.append({
                "image_id": m.image_id,
                "is_best": m.is_best,
                "user_choice": m.user_choice,
                "image": _image_to_dict(img) if img else None,
            })
        result.append({
            "id": g.id,
            "match_type": g.match_type,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "members": members,
        })

        # Count by match_type (across all unresolved, not just this page)
        type_count_q = (
            sa_select(DuplicateGroup.match_type, func.count(DuplicateGroup.id))
            .where(DuplicateGroup.id.notin_(sa_select(resolved_subq.c.group_id)))
            .group_by(DuplicateGroup.match_type)
        )
        type_counts_result = await session.execute(type_count_q)
        match_type_counts = dict(type_counts_result.all())

    return {"groups": result, "total": total, "page": page, "limit": limit, "match_type_counts": match_type_counts}


@router.get("/duplicates/{group_id}")
async def get_duplicate_group(request: Request, group_id: int) -> Dict[str, Any]:
    from sqlalchemy import select
    from backend.db.models import DuplicateGroup, DuplicateGroupMember

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(
            select(DuplicateGroup).where(DuplicateGroup.id == group_id)
        )
        group = result.scalar_one_or_none()
        if group is None:
            raise HTTPException(status_code=404, detail="Duplicate group not found")

        member_result = await session.execute(
            select(DuplicateGroupMember).where(DuplicateGroupMember.group_id == group_id)
        )
        members = list(member_result.scalars().all())

        member_dicts = []
        for member in members:
            img_result = await session.execute(select(Image).where(Image.id == member.image_id))
            img = img_result.scalar_one_or_none()
            member_dicts.append(
                {
                    "image_id": member.image_id,
                    "is_best": member.is_best,
                    "user_choice": member.user_choice,
                    "image": _image_to_dict(img) if img is not None else None,
                }
            )

    return {
        "id": group.id,
        "match_type": group.match_type,
        "created_at": group.created_at.isoformat() if group.created_at is not None else None,
        "members": member_dicts,
    }


class ResolveBody(BaseModel):
    keep: List[int]
    reject: List[int]


@router.get("/version")
async def get_app_version() -> Dict[str, str]:
    """Return the running app version (single source: pyproject.toml)."""
    from backend.version import get_version

    return {"version": get_version()}


@router.get("/errors/summary")
async def get_errors_summary(request: Request) -> Dict[str, Any]:
    """Errored images grouped by cause, plus error/missing totals."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        return await errors_summary(session)


class RetryErrorsBody(BaseModel):
    cause: Optional[str] = None


@router.post("/errors/retry")
async def post_retry_errors(request: Request, body: RetryErrorsBody) -> Dict[str, Any]:
    """Reset errored images to pending so they get reprocessed on the next run.

    Optionally restrict to a single ``cause`` (error_message). Trigger
    ``POST /indexer/process`` afterwards to actually reprocess them.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        reset = await retry_errored(session, cause=body.cause)
    return {"reset": reset}


class BulkResolveBody(BaseModel):
    match_types: Optional[List[str]] = None
    exclude_burst: bool = True
    dry_run: bool = False


@router.post("/duplicates/bulk-resolve")
async def bulk_resolve(request: Request, body: BulkResolveBody) -> Dict[str, Any]:
    """Auto-resolve copy-type duplicate groups (keep best, reject the rest).

    Bursts are excluded by default. Use ``dry_run: true`` to preview the impact
    (group/image counts and reclaimable bytes) before applying.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        summary = await bulk_resolve_duplicates(
            session,
            exclude_burst=body.exclude_burst,
            match_types=body.match_types,
            dry_run=body.dry_run,
        )
    return summary


@router.post("/duplicates/{group_id}/resolve")
async def resolve_duplicate(
    request: Request, group_id: int, body: ResolveBody
) -> Dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        await resolve_duplicate_group(
            session=session,
            group_id=group_id,
            keep_ids=body.keep,
            reject_ids=body.reject,
        )
    return {"status": "resolved"}


class UnresolveBody(BaseModel):
    statuses: Dict[int, str] = {}


@router.post("/duplicates/{group_id}/unresolve")
async def unresolve_duplicate(
    request: Request, group_id: int, body: UnresolveBody
) -> Dict[str, Any]:
    """Undo a duplicate-group resolution, restoring the given prior statuses."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        found = await unresolve_duplicate_group(
            session=session, group_id=group_id, statuses=body.statuses
        )
    if not found:
        raise HTTPException(status_code=404, detail="Duplicate group not found")
    return {"status": "unresolved"}


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


@router.get("/indexer/status")
async def indexer_status(request: Request) -> Dict[str, Any]:
    from sqlalchemy import select, func
    orchestrator = request.app.state.orchestrator
    result = orchestrator.state.to_dict()

    # Add database-level summary
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        counts_result = await session.execute(
            select(Image.status, func.count(Image.id)).group_by(Image.status)
        )
        counts = dict(counts_result.all())

        # Count videos
        from backend.indexer.scanner import VIDEO_EXTENSIONS
        video_exts_upper = [ext.upper().lstrip(".") for ext in VIDEO_EXTENSIONS]
        video_result = await session.execute(
            select(func.count(Image.id)).where(
                Image.format.in_(video_exts_upper),
                Image.status.notin_(["missing", "error"]),
            )
        )
        video_count = video_result.scalar() or 0

        # Count images with/without AI descriptions
        ai_done_result = await session.execute(
            select(func.count(Image.id)).where(
                Image.ai_description.is_not(None),
                Image.status.notin_(["missing", "error", "rejected"]),
            )
        )
        ai_done = ai_done_result.scalar() or 0

        ai_missing_result = await session.execute(
            select(func.count(Image.id)).where(
                Image.ai_description.is_(None),
                Image.status.notin_(["missing", "error", "rejected", "pending"]),
            )
        )
        ai_missing = ai_missing_result.scalar() or 0

        # Count images with file hashes
        hash_result = await session.execute(
            select(func.count(Image.id)).where(
                Image.file_hash.is_not(None),
                Image.status.notin_(["missing", "error"]),
            )
        )
        hash_count = hash_result.scalar() or 0

        # Count images with GPS and location names
        gps_result = await session.execute(
            select(func.count(Image.id)).where(
                Image.exif_gps_lat.is_not(None),
                Image.status.notin_(["missing", "error"]),
            )
        )
        gps_count = gps_result.scalar() or 0

        geocoded_result = await session.execute(
            select(func.count(Image.id)).where(
                Image.location_name.is_not(None),
                Image.status.notin_(["missing", "error"]),
            )
        )
        geocoded_count = geocoded_result.scalar() or 0

        # Format breakdown (top formats by count, excluding missing/error)
        format_result = await session.execute(
            select(Image.format, func.count(Image.id))
            .where(Image.status.notin_(["missing", "error"]))
            .group_by(Image.format)
            .order_by(func.count(Image.id).desc())
        )
        format_counts = {(fmt or "?").upper(): cnt for fmt, cnt in format_result.all()}

        # Status x media type breakdown
        video_by_status_result = await session.execute(
            select(Image.status, func.count(Image.id))
            .where(Image.format.in_(video_exts_upper))
            .group_by(Image.status)
        )
        video_by_status = dict(video_by_status_result.all())

    result["db_summary"] = {
        "total": sum(counts.values()),
        "pending": counts.get("pending", 0),
        "indexed": counts.get("indexed", 0),
        "kept": counts.get("kept", 0),
        "rejected": counts.get("rejected", 0),
        "error": counts.get("error", 0),
        "missing": counts.get("missing", 0),
        "videos": video_count,
        "ai_done": ai_done,
        "ai_missing": ai_missing,
        "formats": format_counts,
        "videos_pending": video_by_status.get("pending", 0),
        "videos_indexed": video_by_status.get("indexed", 0) + video_by_status.get("kept", 0),
        "gps_count": gps_count,
        "geocoded_count": geocoded_count,
        "hash_count": hash_count,
    }
    return result


@router.post("/indexer/start")
async def indexer_start(request: Request) -> Dict[str, Any]:
    orchestrator = request.app.state.orchestrator
    if orchestrator.state.running:
        # Double-check: if _task is done, reset state (stale running flag)
        if hasattr(orchestrator, '_task') and orchestrator._task and orchestrator._task.done():
            orchestrator.state.running = False
        else:
            raise HTTPException(status_code=409, detail="Indexer is already running")
    task = asyncio.create_task(orchestrator.run_full())
    orchestrator._task = task
    return {"status": "started"}


@router.post("/indexer/process")
async def indexer_process(request: Request) -> Dict[str, Any]:
    """Run only metadata + AI on already-scanned images (no folder scan)."""
    orchestrator = request.app.state.orchestrator
    if orchestrator.state.running:
        if hasattr(orchestrator, '_task') and orchestrator._task and orchestrator._task.done():
            orchestrator.state.running = False
        else:
            raise HTTPException(status_code=409, detail="Indexer is already running")

    async def _process_only():
        orchestrator._stop_event.clear()
        orchestrator.state.running = True
        orchestrator._notify()
        try:
            await orchestrator.process_metadata()
            if not orchestrator._stop_event.is_set():
                await orchestrator.process_ai()
            if not orchestrator._stop_event.is_set():
                await orchestrator.process_geocoding()
            if not orchestrator._stop_event.is_set():
                await orchestrator.process_gps_inheritance()
            if not orchestrator._stop_event.is_set():
                await orchestrator._evict_cloud_files()
            orchestrator.state.phase = "complete"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("process_only error: %s", exc)
            orchestrator.state.phase = "error"
        finally:
            orchestrator.state.running = False
            orchestrator._notify()

    task = asyncio.create_task(_process_only())
    orchestrator._task = task
    return {"status": "processing"}


@router.post("/indexer/stop")
async def indexer_stop(request: Request) -> Dict[str, Any]:
    orchestrator = request.app.state.orchestrator
    orchestrator.request_stop()
    return {"status": "stopping"}


@router.post("/indexer/find-duplicates")
async def indexer_find_duplicates(request: Request) -> Dict[str, Any]:
    """Manually trigger duplicate grouping (file hash + pHash + burst detection)."""
    orchestrator = request.app.state.orchestrator
    if orchestrator.state.running:
        if hasattr(orchestrator, '_task') and orchestrator._task and orchestrator._task.done():
            orchestrator.state.running = False
        else:
            raise HTTPException(status_code=409, detail="Indexer is already running")

    async def _find_duplicates():
        orchestrator._stop_event.clear()
        orchestrator.state.running = True
        orchestrator._notify()
        try:
            await orchestrator.group_duplicates()
            orchestrator.state.phase = "complete"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("find_duplicates error: %s", exc)
            orchestrator.state.phase = "error"
        finally:
            orchestrator.state.running = False
            orchestrator._notify()

    task = asyncio.create_task(_find_duplicates())
    orchestrator._task = task
    return {"status": "started"}


@router.post("/indexer/compute-hashes")
async def indexer_compute_hashes(request: Request) -> Dict[str, Any]:
    """Compute SHA-256 file hashes for images that don't have one yet."""
    orchestrator = request.app.state.orchestrator
    if orchestrator.state.running:
        if hasattr(orchestrator, '_task') and orchestrator._task and orchestrator._task.done():
            orchestrator.state.running = False
        else:
            raise HTTPException(status_code=409, detail="Indexer is already running")

    async def _compute_hashes():
        orchestrator._stop_event.clear()
        orchestrator.state.running = True
        orchestrator._notify()
        try:
            await orchestrator.process_file_hashes()
            orchestrator.state.phase = "complete"
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("compute_hashes error: %s", exc)
            orchestrator.state.phase = "error"
        finally:
            orchestrator.state.running = False
            orchestrator._notify()

    task = asyncio.create_task(_compute_hashes())
    orchestrator._task = task
    return {"status": "started"}


# ---------------------------------------------------------------------------
# Map clusters
# ---------------------------------------------------------------------------


@router.get("/map/clusters")
async def map_clusters(
    request: Request,
    zoom: int = 10,
    south: Optional[float] = None,
    north: Optional[float] = None,
    west: Optional[float] = None,
    east: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_inherited: bool = True,
) -> List[Dict[str, Any]]:
    """Return clustered image locations for the map view.

    Cluster precision depends on zoom level:
    - zoom 1-7:  0 decimals (~111km)
    - zoom 8-10: 1 decimal (~11km)
    - zoom 11-13: 2 decimals (~1.1km)
    - zoom 14-16: 3 decimals (~110m)
    - zoom 17+: 4 decimals (~11m) — individual images
    """
    from sqlalchemy import func as sqlfunc, text, literal_column

    if zoom <= 7:
        precision = 0
    elif zoom <= 10:
        precision = 1
    elif zoom <= 13:
        precision = 2
    elif zoom <= 16:
        precision = 3
    else:
        precision = 4

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        # Round coordinates for clustering
        rlat = sqlfunc.round(Image.exif_gps_lat, precision)
        rlon = sqlfunc.round(Image.exif_gps_lon, precision)

        stmt = (
            select(
                sqlfunc.avg(Image.exif_gps_lat).label("lat"),
                sqlfunc.avg(Image.exif_gps_lon).label("lon"),
                sqlfunc.count(Image.id).label("count"),
                sqlfunc.min(Image.id).label("sample_id"),
            )
            .where(
                Image.exif_gps_lat.is_not(None),
                Image.status.notin_(["missing", "error", "rejected"]),
            )
            .group_by(rlat, rlon)
        )

        if not include_inherited:
            stmt = stmt.where(Image.gps_inherited == False)

        if south is not None and north is not None:
            stmt = stmt.where(Image.exif_gps_lat >= south, Image.exif_gps_lat <= north)
        if west is not None and east is not None:
            stmt = stmt.where(Image.exif_gps_lon >= west, Image.exif_gps_lon <= east)
        if date_from:
            stmt = stmt.where(Image.exif_date >= date_from)
        if date_to:
            stmt = stmt.where(Image.exif_date <= date_to + "T23:59:59")

        result = await session.execute(stmt)
        rows = result.all()

        # Get location names for clusters (from sample image)
        sample_ids = [r.sample_id for r in rows]
        loc_names: dict[int, str] = {}
        if sample_ids:
            loc_result = await session.execute(
                select(Image.id, Image.location_name).where(Image.id.in_(sample_ids))
            )
            loc_names = {r.id: r.location_name for r in loc_result.all() if r.location_name}

    return [
        {
            "lat": float(r.lat),
            "lon": float(r.lon),
            "count": r.count,
            "sample_id": r.sample_id,
            "location_name": loc_names.get(r.sample_id),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


@router.get("/geocode")
async def geocode_search(q: str) -> List[Dict[str, Any]]:
    """Forward geocode a place name using OpenStreetMap Nominatim.

    Returns a list of matching places with coordinates and bounding boxes.
    """
    import httpx

    if not q or len(q.strip()) < 2:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": 5,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "Fotoxi/1.0", "Accept-Language": "fi,en"},
            )
            resp.raise_for_status()
            results = resp.json()
    except Exception:
        return []

    places = []
    for r in results:
        bbox = r.get("boundingbox", [])
        # Nominatim bbox: [south_lat, north_lat, west_lon, east_lon]
        lat = float(r["lat"])
        lon = float(r["lon"])

        # Calculate radius from bounding box (diagonal / 2 in km)
        if len(bbox) == 4:
            import math
            lat_span = abs(float(bbox[1]) - float(bbox[0]))
            lon_span = abs(float(bbox[3]) - float(bbox[2]))
            radius_km = max(
                lat_span * 111.0 / 2,
                lon_span * 111.0 * math.cos(math.radians(lat)) / 2,
            )
            # Clamp to reasonable range
            radius_km = max(0.5, min(radius_km, 200.0))
        else:
            radius_km = 10.0

        # Build display name from address parts
        addr = r.get("address", {})
        display = r.get("display_name", q)

        places.append({
            "display_name": display,
            "lat": lat,
            "lon": lon,
            "radius_km": round(radius_km, 1),
            "type": r.get("type", ""),
            "address": addr,
        })

    return places


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingsUpdate(BaseModel):
    source_dirs: Optional[List[str]] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ai_language: Optional[str] = None
    ai_quality_enabled: Optional[bool] = None
    phash_threshold: Optional[int] = None
    burst_time_window: Optional[float] = None
    thread_pool_size: Optional[int] = None
    ollama_concurrency: Optional[int] = None
    server_host: Optional[str] = None
    server_port: Optional[int] = None
    exclude_patterns: Optional[List[str]] = None
    auto_process_on_start: Optional[bool] = None
    ui_language: Optional[str] = None
    custom_tag_label: Optional[str] = None
    dup_confirm_quick_actions: Optional[bool] = None


@router.get("/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    config = request.app.state.config
    # Load persisted settings from DB into config
    await _load_settings_from_db(request)
    return dataclasses.asdict(config)


@router.get("/cloud-folders")
async def list_cloud_folders() -> List[Dict[str, str]]:
    """List available cloud storage folders (macOS CloudStorage)."""
    cloud_dir = Path.home() / "Library" / "CloudStorage"
    result = []
    if cloud_dir.is_dir():
        for entry in sorted(cloud_dir.iterdir()):
            if entry.is_dir():
                name = entry.name
                if "OneDrive" in name:
                    label = f"OneDrive ({name.split('-', 1)[-1] if '-' in name else name})"
                elif "GoogleDrive" in name:
                    label = f"Google Drive ({name.split('-', 1)[-1] if '-' in name else name})"
                elif "Dropbox" in name:
                    label = f"Dropbox"
                else:
                    label = name
                result.append({"label": label, "path": str(entry)})
    # iCloud Drive
    icloud = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if icloud.is_dir():
        result.append({"label": "iCloud Drive", "path": str(icloud)})
    # Also add ~/Pictures if it exists
    pictures = Path.home() / "Pictures"
    if pictures.is_dir():
        result.append({"label": "Kuvat (Pictures)", "path": str(pictures)})
    return result


@router.get("/browse")
async def browse_directory(path: str = "~") -> Dict[str, Any]:
    """List subdirectories for folder picker UI."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise HTTPException(status_code=404, detail="Not a directory")
    dirs = []
    try:
        for entry in sorted(resolved.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                dirs.append({"name": entry.name, "path": str(entry)})
    except PermissionError:
        pass
    return {"current": str(resolved), "parent": str(resolved.parent), "dirs": dirs}


@router.put("/settings")
async def update_settings(request: Request, body: SettingsUpdate) -> Dict[str, Any]:
    config = request.app.state.config
    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        if hasattr(config, key):
            setattr(config, key, value)
    # Persist to DB
    await _save_settings_to_db(request)
    return dataclasses.asdict(config)


async def _load_settings_from_db(request: Request) -> None:
    """Load persisted settings from the settings table into config."""
    from sqlalchemy import select as sa_select
    from backend.db.models import Setting

    config = request.app.state.config
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(sa_select(Setting))
        rows = result.scalars().all()
        for row in rows:
            try:
                value = json.loads(row.value)
                if hasattr(config, row.key):
                    setattr(config, row.key, value)
            except (json.JSONDecodeError, TypeError):
                pass


async def _save_settings_to_db(request: Request) -> None:
    """Persist current config to the settings table."""
    from sqlalchemy import select as sa_select
    from backend.db.models import Setting

    config = request.app.state.config
    session_factory = request.app.state.session_factory

    # Save key settings that should persist between restarts
    persist_keys = [
        "source_dirs", "ollama_model", "ollama_url", "ai_language",
        "ai_quality_enabled", "phash_threshold", "burst_time_window",
        "ollama_concurrency", "exclude_patterns", "auto_process_on_start", "ui_language",
        "custom_tag_label", "dup_confirm_quick_actions",
    ]
    config_dict = dataclasses.asdict(config)

    async with session_factory() as session:
        for key in persist_keys:
            if key not in config_dict:
                continue
            value_json = json.dumps(config_dict[key])
            result = await session.execute(
                sa_select(Setting).where(Setting.key == key)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.value = value_json
            else:
                session.add(Setting(key=key, value=value_json))
        await session.commit()
