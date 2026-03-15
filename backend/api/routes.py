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
    get_duplicate_groups,
    resolve_duplicate_group,
    search_images,
)
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
        "exif_focal_length": img.exif_focal_length,
        "exif_aperture": img.exif_aperture,
        "exif_iso": img.exif_iso,
        "exif_exposure": img.exif_exposure,
        "ai_description": img.ai_description,
        "ai_tags": ai_tags,
        "ai_quality_score": img.ai_quality_score,
        "ai_model": img.ai_model,
        "status": img.status,
        "error_message": img.error_message,
        "indexed_at": img.indexed_at.isoformat() if img.indexed_at is not None else None,
        "created_at": img.created_at.isoformat() if img.created_at is not None else None,
        "updated_at": img.updated_at.isoformat() if img.updated_at is not None else None,
    }


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


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
async def get_image_full(request: Request, image_id: int) -> FileResponse:
    from sqlalchemy import select
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.id == image_id))
        img = result.scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")
    file_path = Path(img.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")
    # Guess media type from extension for proper video playback
    import mimetypes
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
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
        img.status = body.status
        await session.commit()
    return {"id": image_id, "status": body.status}


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


@router.get("/duplicates")
async def list_duplicates(
    request: Request,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    session_factory = request.app.state.session_factory
    pending_only = status == "pending"
    async with session_factory() as session:
        groups = await get_duplicate_groups(session=session, pending_only=pending_only)

    # Serialize Image objects inside member dicts
    result = []
    for group in groups:
        members = []
        for member in group["members"]:
            m = dict(member)
            if m.get("image") is not None:
                m["image"] = _image_to_dict(m["image"])
            members.append(m)
        result.append(
            {
                "id": group["id"],
                "match_type": group["match_type"],
                "created_at": group["created_at"].isoformat() if group["created_at"] is not None else None,
                "members": members,
            }
        )
    return result


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
                await orchestrator.group_duplicates()
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
        "ollama_concurrency", "exclude_patterns", "auto_process_on_start",
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
