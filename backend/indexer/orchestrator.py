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

logger = logging.getLogger(__name__)


@dataclass
class IndexerState:
    running: bool = False
    phase: str = "idle"  # idle/scanning/metadata/ai_analysis/complete/error
    total: int = 0
    processed: int = 0
    errors: int = 0
    speed: float = 0.0  # items per second

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "phase": self.phase,
            "total": self.total,
            "processed": self.processed,
            "errors": self.errors,
            "speed": self.speed,
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
        self._notify()

        # Collect all paths found on disk across all source directories
        found_paths: set[str] = set()

        for source_dir in self.config.source_dirs:
            for file_path in scan_directory(source_dir):
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
                        # Re-index if size or mtime changed
                        if existing.file_size != file_size or existing.file_mtime != file_mtime:
                            existing.file_size = file_size
                            existing.file_mtime = file_mtime
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

        # Mark files that are in DB but no longer on disk as "missing"
        async with self.session_factory() as session:
            result = await session.execute(select(Image))
            all_images = result.scalars().all()
            for image in all_images:
                if self._stop_event.is_set():
                    return
                if image.file_path not in found_paths and image.status != "missing":
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
                if self._stop_event.is_set():
                    logger.info("process_metadata: stop requested, aborting")
                    return

                image_id = image.id
                file_path = Path(image.file_path)

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

                        await session.commit()

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

    async def process_ai(self) -> None:
        """Run AI analysis on images that have phash but are still pending."""
        self.state.phase = "ai_analysis"
        self.state.processed = 0
        self.state.errors = 0
        self._notify()

        # Images where phash is not null and status is still "pending"
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
                    Image.phash.is_not(None),
                    Image.status == "pending",
                )
            )
            candidates = result.scalars().all()

        self.state.total = len(candidates)
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

            async with semaphore:
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

                    self.state.processed += 1

                except Exception as exc:
                    logger.error("process_ai: error for %s: %s", file_path, exc)
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

        await asyncio.gather(*[_process_one(img) for img in candidates])

    # ------------------------------------------------------------------
    # Top-level orchestration
    # ------------------------------------------------------------------

    async def run_full(self) -> None:
        """Run all indexing phases sequentially."""
        self.state.running = True
        # Only clear stop_event if not already requested before this call
        if not self._stop_event.is_set():
            self._stop_event.clear()
        self._notify()

        try:
            await self.scan()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            await self.process_metadata()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            await self.process_ai()
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
