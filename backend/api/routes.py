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
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        images, total = await search_images(
            session=session,
            q=q,
            date_from=date_from,
            date_to=date_to,
            camera=camera,
            min_quality=min_quality,
            status=status,
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
    return FileResponse(str(file_path))


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
    orchestrator = request.app.state.orchestrator
    return orchestrator.state.to_dict()


@router.post("/indexer/start")
async def indexer_start(request: Request) -> Dict[str, Any]:
    orchestrator = request.app.state.orchestrator
    if orchestrator.state.running:
        raise HTTPException(status_code=409, detail="Indexer is already running")
    asyncio.create_task(orchestrator.run_full())
    return {"status": "started"}


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


@router.get("/settings")
async def get_settings(request: Request) -> Dict[str, Any]:
    config = request.app.state.config
    return dataclasses.asdict(config)


@router.put("/settings")
async def update_settings(request: Request, body: SettingsUpdate) -> Dict[str, Any]:
    config = request.app.state.config
    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        if hasattr(config, key):
            setattr(config, key, value)
    return dataclasses.asdict(config)
