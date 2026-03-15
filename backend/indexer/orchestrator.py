from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import Config
from backend.db.models import Image
from backend.indexer.analyzer import analyze_image
from backend.indexer.eviction import evict_file, is_cloud_path
from backend.indexer.exif import extract_exif
from backend.indexer.hasher import compute_hashes
from backend.indexer.scanner import scan_directory
from backend.indexer.thumbnailer import generate_thumbnail
from backend.grouping.duplicates import find_duplicate_groups

logger = logging.getLogger(__name__)


@dataclass
class IndexerState:
    running: bool = False
    phase: str = "idle"  # idle/scanning/metadata/ai_analysis/complete/error
    total: int = 0
    processed: int = 0
    errors: int = 0
    speed: float = 0.0  # items per second
    current_file: str = ""  # file currently being processed
    current_file_path: str = ""  # full path of current file
    current_image_id: int = 0  # DB id for thumbnail
    current_source_dir: str = ""  # source dir being scanned
    completed_source_dirs: list[str] = field(default_factory=list)
    # Separate AI progress (can run in parallel)
    ai_total: int = 0
    ai_processed: int = 0
    ai_speed: float = 0.0
    ai_current_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "phase": self.phase,
            "total": self.total,
            "processed": self.processed,
            "errors": self.errors,
            "speed": self.speed,
            "current_file": self.current_file,
            "current_file_path": self.current_file_path,
            "current_image_id": self.current_image_id,
            "current_source_dir": self.current_source_dir,
            "completed_source_dirs": self.completed_source_dirs,
            "ai_total": self.ai_total,
            "ai_processed": self.ai_processed,
            "ai_speed": self.ai_speed,
            "ai_current_file": self.ai_current_file,
        }


class IndexerOrchestrator:
    def __init__(
        self,
        config: Config,
        session_factory: async_sessionmaker[AsyncSession],
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.config = config
        self.session_factory = session_factory
        self.on_progress = on_progress
        self.state = IndexerState()
        self._stop_event = asyncio.Event()

    def _notify(self) -> None:
        if self.on_progress is not None:
            try:
                self.on_progress(self.state.to_dict())
            except Exception as exc:
                logger.warning("on_progress callback raised: %s", exc)

    # ------------------------------------------------------------------
    # Phase 1: scan
    # ------------------------------------------------------------------

    async def scan(self) -> None:
        """Scan source directories and create/update Image rows."""
        self.state.phase = "scanning"
        self.state.total = 0
        self.state.processed = 0
        self.state.errors = 0
        self.state.current_source_dir = ""
        self.state.completed_source_dirs = []
        self._notify()

        # Collect all paths found on disk across all source directories
        found_paths: set[str] = set()

        for source_dir in self.config.source_dirs:
            self.state.current_source_dir = source_dir
            self._notify()
            for file_path in scan_directory(source_dir, exclude_patterns=self.config.exclude_patterns):
                await asyncio.sleep(0)  # yield to event loop for stop checks
                if self._stop_event.is_set():
                    logger.info("scan: stop requested, aborting")
                    return

                str_path = str(file_path)
                found_paths.add(str_path)

                try:
                    stat = file_path.stat()
                    file_size = stat.st_size
                    file_mtime = stat.st_mtime
                except OSError as exc:
                    logger.warning("scan: cannot stat %s: %s", file_path, exc)
                    self.state.errors += 1
                    continue

                # Detect source_type from path
                source_type = "cloud" if is_cloud_path(file_path) else "local"

                async with self.session_factory() as session:
                    result = await session.execute(
                        select(Image).where(Image.file_path == str_path)
                    )
                    existing: Optional[Image] = result.scalar_one_or_none()

                    if existing is not None:
                        # Re-index if size or mtime changed, but preserve user decisions
                        if existing.file_size != file_size or existing.file_mtime != file_mtime:
                            existing.file_size = file_size
                            existing.file_mtime = file_mtime
                            # Only reset to pending if not a user decision (kept/rejected)
                            if existing.status not in ("kept", "rejected"):
                                existing.status = "pending"
                                existing.error_message = None
                            await session.commit()
                            logger.debug("scan: marked changed file for re-index: %s", str_path)
                    else:
                        # New file
                        image = Image(
                            file_path=str_path,
                            file_name=file_path.name,
                            file_size=file_size,
                            file_mtime=file_mtime,
                            source_type=source_type,
                            status="pending",
                        )
                        session.add(image)
                        await session.commit()
                        logger.debug("scan: added new file: %s", str_path)

                self.state.processed += 1
                self._notify()

            self.state.completed_source_dirs.append(source_dir)
            self._notify()

        self.state.current_source_dir = ""

        # Mark files that are in DB but no longer on disk as "missing"
        async with self.session_factory() as session:
            result = await session.execute(select(Image))
            all_images = result.scalars().all()
            for image in all_images:
                if self._stop_event.is_set():
                    return
                if image.file_path not in found_paths and image.status not in ("missing", "kept", "rejected"):
                    image.status = "missing"
                    logger.debug("scan: marked missing file: %s", image.file_path)
            await session.commit()

        self.state.total = self.state.processed
        self._notify()

    # ------------------------------------------------------------------
    # Phase 2: process metadata
    # ------------------------------------------------------------------

    async def process_metadata(self) -> None:
        """Extract EXIF, compute hashes, generate thumbnails for pending images."""
        self.state.phase = "metadata"
        self.state.processed = 0
        self.state.errors = 0
        self._notify()

        # Load all pending images
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(Image.status == "pending")
            )
            pending = result.scalars().all()

        self.state.total = len(pending)
        self._notify()

        if not pending:
            return

        thumbs_dir = Path(self.config.thumbs_dir)
        thread_pool_size = self.config.thread_pool_size

        start_time = time.monotonic()

        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor(max_workers=thread_pool_size) as executor:
            for image in pending:
                await asyncio.sleep(0)  # yield to event loop for stop checks
                if self._stop_event.is_set():
                    logger.info("process_metadata: stop requested, aborting")
                    return

                image_id = image.id
                file_path = Path(image.file_path)
                self.state.current_file = image.file_name
                self.state.current_file_path = image.file_path
                self.state.current_image_id = image.id

                try:
                    # Run blocking calls in thread pool
                    exif_data = await loop.run_in_executor(
                        executor, extract_exif, file_path
                    )
                    hash_data = await loop.run_in_executor(
                        executor, compute_hashes, file_path
                    )
                    await loop.run_in_executor(
                        executor, generate_thumbnail, file_path, thumbs_dir, image_id
                    )

                    async with self.session_factory() as session:
                        result = await session.execute(
                            select(Image).where(Image.id == image_id)
                        )
                        img = result.scalar_one_or_none()
                        if img is None:
                            continue

                        if exif_data:
                            img.width = exif_data.get("width")
                            img.height = exif_data.get("height")
                            img.format = exif_data.get("format")
                            img.exif_date = exif_data.get("exif_date")
                            img.exif_camera_make = exif_data.get("exif_camera_make")
                            img.exif_camera_model = exif_data.get("exif_camera_model")
                            img.exif_gps_lat = exif_data.get("exif_gps_lat")
                            img.exif_gps_lon = exif_data.get("exif_gps_lon")
                            img.exif_focal_length = exif_data.get("exif_focal_length")
                            img.exif_aperture = exif_data.get("exif_aperture")
                            img.exif_iso = exif_data.get("exif_iso")
                            img.exif_exposure = exif_data.get("exif_exposure")

                        if hash_data:
                            img.phash = hash_data.get("phash")
                            img.dhash = hash_data.get("dhash")

                        # Mark as indexed after successful metadata extraction
                        img.status = "indexed"
                        import datetime as _dt
                        img.indexed_at = _dt.datetime.now(_dt.timezone.utc)

                        await session.commit()

                    # Evict cloud file after metadata extraction
                    if is_cloud_path(file_path):
                        await evict_file(file_path)

                    self.state.processed += 1

                except Exception as exc:
                    logger.error("process_metadata: error for %s: %s", file_path, exc)
                    self.state.errors += 1

                    async with self.session_factory() as session:
                        result = await session.execute(
                            select(Image).where(Image.id == image_id)
                        )
                        img = result.scalar_one_or_none()
                        if img is not None:
                            img.status = "error"
                            img.error_message = str(exc)
                            await session.commit()

                elapsed = time.monotonic() - start_time
                total_done = self.state.processed + self.state.errors
                self.state.speed = total_done / elapsed if elapsed > 0 else 0.0
                self._notify()

    # ------------------------------------------------------------------
    # Phase 3: AI analysis
    # ------------------------------------------------------------------

    async def _check_ollama(self) -> bool:
        """Quick check if Ollama is reachable AND can run the model."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Check if server is up
                resp = await client.get(self.config.ollama_url)
                if resp.status_code != 200:
                    return False
                # Test if the model actually works with a simple prompt
                test_resp = await client.post(
                    f"{self.config.ollama_url}/api/chat",
                    json={
                        "model": self.config.ollama_model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                    },
                )
                return test_resp.status_code == 200
        except Exception:
            return False

    async def process_ai(self) -> None:
        """Run AI analysis on images that have phash but are still pending."""
        self.state.phase = "ai_analysis"
        self.state.ai_processed = 0
        self.state.ai_total = 0
        self.state.ai_speed = 0.0
        self.state.ai_current_file = ""
        self._notify()

        # Check if Ollama is running before starting
        if not await self._check_ollama():
            logger.warning("Ollama not reachable at %s, skipping AI analysis", self.config.ollama_url)
            # Mark pending images with metadata as "indexed" (no AI available)
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Image).where(
                        Image.phash.is_not(None),
                        Image.status == "pending",
                    )
                )
                for img in result.scalars().all():
                    img.status = "indexed"
                await session.commit()
            logger.info("Marked pending images as indexed (no AI)")
            return

        # Images with metadata but without AI description
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
                    Image.phash.is_not(None),
                    Image.ai_description.is_(None),
                    Image.status.in_(["pending", "indexed", "kept"]),
                )
            )
            candidates = result.scalars().all()

        self.state.ai_total = len(candidates)
        self._notify()

        if not candidates:
            return

        semaphore = asyncio.Semaphore(self.config.ollama_concurrency)
        loop = asyncio.get_event_loop()
        start_time = time.monotonic()

        async def _process_one(image: Image) -> None:
            if self._stop_event.is_set():
                return

            image_id = image.id
            file_path = Path(image.file_path)
            self.state.ai_current_file = image.file_name

            async with semaphore:
                if self._stop_event.is_set():
                    return
                try:
                    ai_result = await loop.run_in_executor(
                        None,
                        lambda: analyze_image(
                            path=file_path,
                            ollama_url=self.config.ollama_url,
                            model=self.config.ollama_model,
                            language=self.config.ai_language,
                            quality_enabled=self.config.ai_quality_enabled,
                        ),
                    )

                    async with self.session_factory() as session:
                        result = await session.execute(
                            select(Image).where(Image.id == image_id)
                        )
                        img = result.scalar_one_or_none()
                        if img is None:
                            return

                        if ai_result is not None:
                            import datetime

                            img.ai_description = ai_result.get("description")
                            tags = ai_result.get("tags")
                            img.ai_tags = json.dumps(tags) if tags is not None else None
                            img.ai_quality_score = ai_result.get("quality_score")
                            img.ai_model = self.config.ollama_model
                            img.status = "indexed"
                            img.indexed_at = datetime.datetime.utcnow()
                        else:
                            img.status = "error"
                            img.error_message = "AI analysis returned no result"

                        await session.commit()

                    # Evict cloud files after indexing
                    if is_cloud_path(file_path):
                        await evict_file(file_path)

                    self.state.ai_processed += 1

                except Exception as exc:
                    logger.error("process_ai: error for %s: %s", file_path, exc)
                    self.state.ai_processed += 1  # count errors too for progress

                    async with self.session_factory() as session:
                        result = await session.execute(
                            select(Image).where(Image.id == image_id)
                        )
                        img = result.scalar_one_or_none()
                        if img is not None:
                            img.status = "error"
                            img.error_message = str(exc)
                            await session.commit()

                elapsed = time.monotonic() - start_time
                self.state.ai_speed = self.state.ai_processed / elapsed if elapsed > 0 else 0.0
                self._notify()

        await asyncio.gather(*[_process_one(img) for img in candidates])

    # ------------------------------------------------------------------
    # Phase 4: Duplicate grouping
    # ------------------------------------------------------------------

    async def group_duplicates(self) -> None:
        """Find and store duplicate groups based on pHash and burst detection."""
        from backend.db.models import DuplicateGroup, DuplicateGroupMember

        self.state.phase = "grouping"
        self.state.processed = 0
        self.state.errors = 0
        self.state.current_file = ""
        self._notify()

        # Load all images with phash
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
                    Image.phash.is_not(None),
                    Image.status.notin_(["rejected", "missing", "error"]),
                )
            )
            all_images = result.scalars().all()

        if not all_images:
            return

        self.state.total = len(all_images)
        self._notify()

        # Convert to dicts for the grouping algorithm
        image_dicts = [
            {
                "id": img.id,
                "phash": img.phash,
                "exif_date": img.exif_date,
                "exif_camera_model": img.exif_camera_model,
                "file_path": img.file_path,
            }
            for img in all_images
        ]

        logger.info("group_duplicates: analyzing %d images for duplicates", len(image_dicts))
        groups = find_duplicate_groups(
            image_dicts,
            phash_threshold=self.config.phash_threshold,
            burst_window=self.config.burst_time_window,
        )
        logger.info("group_duplicates: found %d raw duplicate groups", len(groups))

        # Filter out groups where ALL members are from Photos Library (internal duplicates)
        PHOTOS_LIB = "Photos Library.photoslibrary"
        id_to_path = {img["id"]: img.get("file_path", "") for img in image_dicts}
        filtered_groups = []
        for g in groups:
            paths = [id_to_path.get(id, "") for id in g["image_ids"]]
            all_photos_lib = all(PHOTOS_LIB in p for p in paths)
            if not all_photos_lib:
                filtered_groups.append(g)
        groups = filtered_groups
        logger.info("group_duplicates: %d groups after filtering Photos Library internals", len(groups))

        # Delete only unresolved groups (preserve user decisions), then add new ones
        async with self.session_factory() as session:
            from sqlalchemy import delete

            # Find groups that have been resolved (any member has user_choice set)
            resolved_result = await session.execute(
                select(DuplicateGroupMember.group_id).where(
                    DuplicateGroupMember.user_choice.is_not(None)
                ).distinct()
            )
            resolved_group_ids = {row[0] for row in resolved_result.all()}

            # Find image IDs already in resolved groups (don't re-group them)
            resolved_image_ids: set[int] = set()
            if resolved_group_ids:
                resolved_members_result = await session.execute(
                    select(DuplicateGroupMember.image_id).where(
                        DuplicateGroupMember.group_id.in_(resolved_group_ids)
                    )
                )
                resolved_image_ids = {row[0] for row in resolved_members_result.all()}

            # Delete only unresolved groups
            unresolved_members = delete(DuplicateGroupMember).where(
                DuplicateGroupMember.group_id.notin_(resolved_group_ids) if resolved_group_ids else True
            )
            await session.execute(unresolved_members)
            unresolved_groups = delete(DuplicateGroup).where(
                DuplicateGroup.id.notin_(resolved_group_ids) if resolved_group_ids else True
            )
            await session.execute(unresolved_groups)
            await session.commit()

            # Create new groups, excluding images already in resolved groups
            for group_data in groups:
                new_ids = [id for id in group_data["image_ids"] if id not in resolved_image_ids]
                if len(new_ids) < 2:
                    continue  # Need at least 2 for a duplicate group

                group = DuplicateGroup(match_type=group_data["match_type"])
                session.add(group)
                await session.flush()

                for image_id in new_ids:
                    member = DuplicateGroupMember(
                        group_id=group.id,
                        image_id=image_id,
                        is_best=False,
                    )
                    session.add(member)

            await session.commit()

        self.state.processed = len(groups)
        self._notify()

    # ------------------------------------------------------------------
    # Top-level orchestration
    # ------------------------------------------------------------------

    async def run_full(self) -> None:
        """Run all indexing phases. AI runs after metadata, or in parallel if
        there are already-indexed images without AI descriptions."""
        self._stop_event.clear()
        self.state.running = True
        self.state.phase = "starting"
        self._notify()

        try:
            await self.scan()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # Check if there are images needing AI (already indexed but no description)
            has_ai_work = False
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Image.id).where(
                        Image.ai_description.is_(None),
                        Image.phash.is_not(None),
                        Image.status.in_(["indexed", "kept"]),
                    ).limit(1)
                )
                has_ai_work = result.scalar_one_or_none() is not None

            # Check if there are pending images needing metadata
            has_metadata_work = False
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Image.id).where(Image.status == "pending").limit(1)
                )
                has_metadata_work = result.scalar_one_or_none() is not None

            if has_metadata_work and has_ai_work:
                # Run both in parallel
                logger.info("run_full: running metadata and AI in parallel")
                await asyncio.gather(
                    self.process_metadata(),
                    self.process_ai(),
                    return_exceptions=True,
                )
            else:
                if has_metadata_work:
                    await self.process_metadata()
                if self._stop_event.is_set():
                    self.state.phase = "idle"
                    return
                await self.process_ai()

            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            await self.group_duplicates()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            self.state.phase = "complete"
        except Exception as exc:
            logger.error("run_full: unhandled error: %s", exc)
            self.state.phase = "error"
        finally:
            self.state.running = False
            self._notify()

    def request_stop(self) -> None:
        """Signal the orchestrator to stop after the current item."""
        self._stop_event.set()
