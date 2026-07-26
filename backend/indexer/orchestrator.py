from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import Config
from backend.db.models import Image
from backend.indexer.analyzer import analyze_image
from backend.indexer.eviction import evict_file, is_cloud_path, is_icloud_path
from backend.indexer.exif import extract_exif
from backend.indexer.geocoder import batch_reverse_geocode
from backend.indexer.hasher import compute_hashes
from backend.indexer.scanner import scan_directory
from backend.indexer.thumbnailer import generate_thumbnail, extract_video_keyframes
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
    recent_log: list[str] = field(default_factory=list)  # Last N log entries

    def log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.recent_log.append(f"[{ts}] {msg}")
        if len(self.recent_log) > 20:
            self.recent_log = self.recent_log[-20:]

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
            "recent_log": self.recent_log[-10:],
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

    async def scan(self) -> int:
        """Scan source directories and create/update Image rows.

        Returns the number of image rows created or updated during this run
        (new files added, existing files whose size/mtime changed, and files
        marked missing because they disappeared from disk).
        """
        changed_count = 0
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
                    return changed_count

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
                        # Re-index if size or mtime changed, or if the row says the file
                        # went missing but it is on disk again — a restored file can come
                        # back byte-identical, so size/mtime alone would never notice it.
                        changed_on_disk = (
                            existing.file_size != file_size
                            or existing.file_mtime != file_mtime
                        )
                        if changed_on_disk or existing.status == "missing":
                            existing.file_size = file_size
                            existing.file_mtime = file_mtime
                            if changed_on_disk:
                                # Content may differ, so file_hash is now stale.
                                # process_file_hashes() refills file_hash for any status
                                # except missing/error, so clearing it is always safe.
                                existing.file_hash = None
                            # Only reset to pending if not a user decision (kept/rejected)
                            if existing.status not in ("kept", "rejected"):
                                if changed_on_disk:
                                    # phash is only recomputed by process_metadata(), which
                                    # runs on pending rows — so only clear it when the row
                                    # is actually going back to pending. Nulling it for a
                                    # kept/rejected row would lose it permanently, since
                                    # nothing would ever recompute it.
                                    existing.phash = None
                                existing.status = "pending"
                                existing.error_message = None
                            await session.commit()
                            changed_count += 1
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
                        changed_count += 1
                        logger.debug("scan: added new file: %s", str_path)

                self.state.processed += 1
                self._notify()

            self.state.completed_source_dirs.append(source_dir)
            self._notify()

        self.state.current_source_dir = ""

        # Mark files that are in DB but no longer on disk as "missing"
        import datetime as _dt
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(Image.status != "missing")
            )
            all_images = result.scalars().all()
            missing_count = 0
            for image in all_images:
                if self._stop_event.is_set():
                    return changed_count + missing_count
                if image.file_path not in found_paths:
                    image.status = "missing"
                    image.status_changed_at = _dt.datetime.utcnow()
                    missing_count += 1
                    logger.debug("scan: marked missing file: %s", image.file_path)
            await session.commit()
            if missing_count:
                self.state.log(f"🗑 {missing_count} missing files marked")
                logger.info("scan: marked %d files as missing", missing_count)

        self.state.total = self.state.processed
        self._notify()
        return changed_count + missing_count

    # ------------------------------------------------------------------
    # Phase 2: process metadata
    # ------------------------------------------------------------------

    def _process_one_image_sync(self, file_path: Path, thumbs_dir: Path, image_id: int) -> dict:
        """Process a single image synchronously (runs in thread pool).
        Returns dict with exif_data, hash_data, and success flag."""
        result = {"exif_data": None, "hash_data": None, "error": None}
        try:
            # These all run in the same thread - no context switching overhead
            result["exif_data"] = extract_exif(file_path)
            result["hash_data"] = compute_hashes(file_path)
            generate_thumbnail(file_path, thumbs_dir, image_id)
        except Exception as exc:
            result["error"] = str(exc)
        return result

    async def process_metadata(self) -> None:
        """Extract EXIF, compute hashes, generate thumbnails for pending images.
        Processes multiple images in parallel using a thread pool with prefetching."""
        self.state.phase = "metadata"
        self.state.processed = 0
        self.state.errors = 0
        self._notify()

        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(Image.status == "pending")
            )
            pending = result.scalars().all()

        self.state.total = len(pending)
        self._notify()

        if not pending:
            return

        # Sort: small files first, large videos last (avoid blocking pipeline)
        pending.sort(key=lambda img: img.file_size or 0)

        thumbs_dir = Path(self.config.thumbs_dir)
        local_concurrency = max(self.config.thread_pool_size, 8)
        cloud_concurrency = 5  # Cloud files download slowly, don't overwhelm
        start_time = time.monotonic()
        loop = asyncio.get_event_loop()
        local_sem = asyncio.Semaphore(local_concurrency)
        cloud_sem = asyncio.Semaphore(cloud_concurrency)

        async def _process_one(image: Image) -> None:
            if self._stop_event.is_set():
                return
            file_path = Path(image.file_path)
            sem = cloud_sem if is_cloud_path(file_path) else local_sem
            async with sem:
                if self._stop_event.is_set():
                    return

                image_id = image.id
                self.state.current_file = image.file_name
                self.state.current_file_path = image.file_path
                self.state.current_image_id = image.id
                is_cloud = is_cloud_path(file_path)
                size_mb = (image.file_size or 0) / 1024 / 1024
                self.state.log(f"{'↓' if is_cloud else '→'} {image.file_name} ({size_mb:.1f} MB)")

                try:
                    # Timeout: 120s for cloud files (download), 30s for local
                    timeout = 120.0 if is_cloud_path(file_path) else 30.0
                    proc_result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            self._process_one_image_sync,
                            file_path, thumbs_dir, image_id,
                        ),
                        timeout=timeout,
                    )

                    if proc_result["error"]:
                        raise Exception(proc_result["error"])

                    exif_data = proc_result["exif_data"]
                    hash_data = proc_result["hash_data"]

                    async with self.session_factory() as session:
                        result = await session.execute(
                            select(Image).where(Image.id == image_id)
                        )
                        img = result.scalar_one_or_none()
                        if img is None:
                            return

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
                            img.file_hash = hash_data.get("file_hash")

                        import datetime as _dt
                        _now = _dt.datetime.utcnow()
                        img.status = "indexed"
                        img.indexed_at = _now
                        img.updated_at = _now
                        await session.commit()

                    self.state.processed += 1
                    self.state.log(f"✓ {image.file_name}")

                except asyncio.TimeoutError:
                    logger.warning("process_metadata: timeout for %s (%.0f MB)", file_path, (image.file_size or 0) / 1024 / 1024)
                    self.state.errors += 1
                    async with self.session_factory() as session:
                        result = await session.execute(select(Image).where(Image.id == image_id))
                        img = result.scalar_one_or_none()
                        if img is not None:
                            img.status = "error"
                            img.error_message = "Timeout - file too large or slow to download"
                            await session.commit()

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

        # Process in batches - semaphores handle actual concurrency
        BATCH = 20  # Small batches for faster progress updates
        for i in range(0, len(pending), BATCH):
            if self._stop_event.is_set():
                break
            batch = pending[i:i + BATCH]
            await asyncio.gather(*[_process_one(img) for img in batch], return_exceptions=True)

    # ------------------------------------------------------------------
    # Phase 2a: File hashes
    # ------------------------------------------------------------------

    async def process_file_hashes(self) -> int:
        """Compute SHA-256 file hashes for images that don't have one yet.

        Only processes locally available files (skips missing/error).
        Returns the number of new hashes computed.
        """
        from backend.indexer.hasher import compute_file_hash

        self.state.phase = "hashing"
        self.state.processed = 0
        self.state.errors = 0
        self._notify()

        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
                    Image.file_hash.is_(None),
                    Image.status.notin_(["missing", "error"]),
                )
            )
            candidates = result.scalars().all()

        if not candidates:
            logger.info("process_file_hashes: all images already have file_hash")
            return 0

        self.state.total = len(candidates)
        self._notify()

        loop = asyncio.get_event_loop()
        local_sem = asyncio.Semaphore(max(self.config.thread_pool_size, 8))
        cloud_sem = asyncio.Semaphore(3)
        start_time = time.monotonic()

        async def _hash_one(image: Image) -> None:
            if self._stop_event.is_set():
                return

            file_path = Path(image.file_path)

            if not file_path.exists():
                self.state.errors += 1
                return

            sem = cloud_sem if is_cloud_path(file_path) else local_sem
            async with sem:
                if self._stop_event.is_set():
                    return

                self.state.current_file = image.file_name
                self._notify()

                try:
                    file_hash = await loop.run_in_executor(
                        None, compute_file_hash, file_path
                    )

                    if file_hash:
                        async with self.session_factory() as session:
                            result = await session.execute(
                                select(Image).where(Image.id == image.id)
                            )
                            img = result.scalar_one_or_none()
                            if img:
                                img.file_hash = file_hash
                                await session.commit()
                        self.state.processed += 1
                    else:
                        self.state.errors += 1

                except Exception as exc:
                    logger.warning("file hash error for %s: %s", file_path, exc)
                    self.state.errors += 1

                elapsed = time.monotonic() - start_time
                total_done = self.state.processed + self.state.errors
                self.state.speed = total_done / elapsed if elapsed > 0 else 0.0
                self._notify()

        # Process in batches
        BATCH = 50
        for i in range(0, len(candidates), BATCH):
            if self._stop_event.is_set():
                break
            batch = candidates[i:i + BATCH]
            await asyncio.gather(*[_hash_one(img) for img in batch], return_exceptions=True)

        self.state.log(f"#️⃣ {self.state.processed} file hashes computed")
        logger.info("process_file_hashes: computed %d hashes", self.state.processed)
        return self.state.processed

    # ------------------------------------------------------------------
    # Phase 2b: Reverse geocoding
    # ------------------------------------------------------------------

    async def process_geocoding(self) -> None:
        """Reverse geocode images that have GPS but no location_name."""
        self.state.phase = "geocoding"
        self.state.processed = 0
        self.state.errors = 0
        self._notify()

        # Find images with GPS but no location_name
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
                    Image.exif_gps_lat.is_not(None),
                    Image.exif_gps_lon.is_not(None),
                    Image.location_name.is_(None),
                    Image.status.notin_(["missing", "error"]),
                )
            )
            candidates = result.scalars().all()

        if not candidates:
            logger.info("process_geocoding: no images need geocoding")
            return

        self.state.total = len(candidates)
        self._notify()

        coords = [
            (img.id, img.exif_gps_lat, img.exif_gps_lon)
            for img in candidates
        ]

        # Build lookup for images needing file_hash
        needs_hash: dict[int, str] = {}
        for img in candidates:
            if img.file_hash is None:
                needs_hash[img.id] = img.file_path

        saved_count = 0
        hashed_count = 0
        loop = asyncio.get_event_loop()

        def _on_progress(done: int, total: int, name: str | None = None, img_count: int = 0) -> None:
            self.state.processed = done
            if name:
                self.state.log(f"📍 {done}/{total} — {name} ({img_count} kuvaa)")
            else:
                self.state.log(f"📍 {done}/{total} — ei tulosta")
            self._notify()

        async def _on_cluster_done(image_ids: list[int], name: str) -> None:
            nonlocal saved_count, hashed_count
            from backend.indexer.hasher import compute_file_hash

            # Compute file hashes for images in this cluster that need one
            hash_updates: dict[int, str] = {}
            for img_id in image_ids:
                if img_id in needs_hash:
                    file_path = Path(needs_hash[img_id])
                    if file_path.exists():
                        fh = await loop.run_in_executor(None, compute_file_hash, file_path)
                        if fh:
                            hash_updates[img_id] = fh
                            hashed_count += 1

            # Save location_name + file_hash in one transaction
            async with self.session_factory() as session:
                await session.execute(
                    update(Image)
                    .where(Image.id.in_(image_ids))
                    .values(location_name=name)
                )
                for img_id, fh in hash_updates.items():
                    await session.execute(
                        update(Image)
                        .where(Image.id == img_id)
                        .values(file_hash=fh)
                    )
                await session.commit()
            saved_count += len(image_ids)

        await batch_reverse_geocode(
            coords,
            on_progress=_on_progress,
            on_cluster_done=_on_cluster_done,
            stop_event=self._stop_event,
        )

        self.state.log(f"📍 Geocoded {saved_count} images" + (f", #️⃣ {hashed_count} hashes" if hashed_count else ""))
        logger.info("process_geocoding: geocoded %d images, computed %d file hashes", saved_count, hashed_count)

    # ------------------------------------------------------------------
    # Phase 2c: GPS inheritance
    # ------------------------------------------------------------------

    async def process_gps_inheritance(self) -> None:
        """Inherit GPS coordinates from nearby photos (same camera, <5min apart)."""
        self.state.phase = "gps_inherit"
        self.state.processed = 0
        self.state.errors = 0
        self._notify()

        # Find images without GPS but with date and camera
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
                    Image.exif_gps_lat.is_(None),
                    Image.exif_date.is_not(None),
                    Image.exif_camera_model.is_not(None),
                    Image.status.notin_(["missing", "error"]),
                )
            )
            candidates = result.scalars().all()

            if not candidates:
                logger.info("process_gps_inheritance: no candidates")
                return

            # Load all GPS images for matching
            gps_result = await session.execute(
                select(Image.id, Image.exif_gps_lat, Image.exif_gps_lon,
                       Image.exif_date, Image.exif_camera_model, Image.location_name).where(
                    Image.exif_gps_lat.is_not(None),
                    Image.gps_inherited == False,
                    Image.status.notin_(["missing", "error"]),
                )
            )
            gps_images = gps_result.all()

        self.state.total = len(candidates)
        self._notify()

        # Index GPS images by camera for fast lookup
        from collections import defaultdict
        gps_by_camera: dict[str, list] = defaultdict(list)
        for row in gps_images:
            if row.exif_camera_model and row.exif_date:
                gps_by_camera[row.exif_camera_model].append(row)

        # Sort each camera group by date for binary search
        for cam_list in gps_by_camera.values():
            cam_list.sort(key=lambda r: r.exif_date)

        inherited = 0
        MAX_SECONDS = 300  # 5 minutes

        for img in candidates:
            if self._stop_event.is_set():
                break

            cam_images = gps_by_camera.get(img.exif_camera_model, [])
            if not cam_images:
                continue

            # Find closest GPS image by time
            best = None
            best_delta = MAX_SECONDS + 1
            for gps_img in cam_images:
                delta = abs((img.exif_date - gps_img.exif_date).total_seconds())
                if delta < best_delta:
                    best_delta = delta
                    best = gps_img
                if delta > MAX_SECONDS and gps_img.exif_date > img.exif_date:
                    break  # sorted, no point checking further

            if best and best_delta <= MAX_SECONDS:
                async with self.session_factory() as session:
                    result = await session.execute(
                        select(Image).where(Image.id == img.id)
                    )
                    db_img = result.scalar_one_or_none()
                    if db_img:
                        db_img.exif_gps_lat = best.exif_gps_lat
                        db_img.exif_gps_lon = best.exif_gps_lon
                        db_img.gps_inherited = True
                        db_img.location_name = best.location_name
                        await session.commit()
                        inherited += 1

            self.state.processed += 1
            self._notify()

        self.state.log(f"📍 Inherited GPS for {inherited} images")
        logger.info("process_gps_inheritance: inherited GPS for %d images", inherited)

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
        """Run AI analysis on indexed images without AI description."""
        self.state.phase = "ai_analysis"
        self.state.ai_processed = 0
        self.state.ai_total = 0
        self.state.ai_speed = 0.0
        self.state.ai_current_file = ""
        self._notify()

        # Check if Ollama is running before starting
        if not await self._check_ollama():
            logger.warning("Ollama not reachable at %s, skipping AI analysis", self.config.ollama_url)
            # Mark pending images as "indexed" (no AI available)
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Image).where(
                        Image.status == "pending",
                    )
                )
                for img in result.scalars().all():
                    img.status = "indexed"
                await session.commit()
            logger.info("Marked pending images as indexed (no AI)")
            return

        # Images without AI description
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image).where(
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

            async with semaphore:
                self.state.ai_current_file = image.file_name
                self._notify()
                if self._stop_event.is_set():
                    return
                try:
                    # For videos, extract keyframes for multi-frame AI analysis
                    from backend.indexer.scanner import VIDEO_EXTENSIONS
                    extra_frames = []
                    if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                        thumbs_dir = Path(self.config.thumbs_dir)
                        extra_frames = await loop.run_in_executor(
                            None,
                            lambda: extract_video_keyframes(file_path, thumbs_dir, image_id, num_frames=3),
                        )

                    ai_result = await loop.run_in_executor(
                        None,
                        lambda: analyze_image(
                            path=file_path,
                            ollama_url=self.config.ollama_url,
                            model=self.config.ollama_model,
                            language=self.config.ai_language,
                            quality_enabled=self.config.ai_quality_enabled,
                            thumb_path=Path(self.config.thumbs_dir) / f"{image_id}.jpg",
                            extra_frames=[str(p) for p in extra_frames],
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

                            desc = ai_result.get("description", "")
                            tags = ai_result.get("tags", [])
                            tags_json = json.dumps(tags) if tags else None
                            lang = self.config.ai_language
                            # Store in generic + language-specific fields
                            img.ai_description = desc
                            img.ai_tags = tags_json
                            if lang == "english" or lang == "en":
                                img.ai_description_en = desc
                                img.ai_tags_en = tags_json
                            elif lang == "finnish" or lang == "fi":
                                img.ai_description_fi = desc
                                img.ai_tags_fi = tags_json
                            img.ai_quality_score = ai_result.get("quality_score")
                            img.ai_model = self.config.ollama_model
                            _now = datetime.datetime.utcnow()
                            img.status = "indexed"
                            img.indexed_at = _now
                            img.updated_at = _now
                            # Log AI result
                            tag_str = ", ".join(tags[:5]) if tags else ""
                            self.state.log(f"🤖 {image.file_name}: {desc[:60]}{'...' if len(desc)>60 else ''}")
                            if tag_str:
                                self.state.log(f"   🏷 {tag_str}")
                        else:
                            img.status = "error"
                            img.error_message = "AI analysis returned no result"

                        await session.commit()

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

        # Load all images with phash or file_hash
        async with self.session_factory() as session:
            from sqlalchemy import or_
            result = await session.execute(
                select(Image).where(
                    or_(Image.phash.is_not(None), Image.file_hash.is_not(None)),
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
                "file_hash": img.file_hash,
                "exif_date": img.exif_date,
                "exif_camera_model": img.exif_camera_model,
                "file_path": img.file_path,
            }
            for img in all_images
        ]

        logger.info("group_duplicates: analyzing %d images for duplicates", len(image_dicts))
        loop = asyncio.get_event_loop()
        groups = await loop.run_in_executor(
            None,
            partial(
                find_duplicate_groups,
                image_dicts,
                phash_threshold=self.config.phash_threshold,
                burst_window=self.config.burst_time_window,
            ),
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
    # Evict cloud files
    # ------------------------------------------------------------------

    async def _evict_cloud_files(self) -> None:
        """Evict cloud files that were downloaded during processing.

        Runs after all phases are complete to ensure no phase needs
        the original file anymore.
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(Image.file_path).where(
                    Image.source_type == "cloud",
                    Image.status.notin_(["missing", "error"]),
                )
            )
            cloud_paths = [row[0] for row in result.all()]

        if not cloud_paths:
            return

        evicted = 0
        skipped = 0
        for fp in cloud_paths:
            if self._stop_event.is_set():
                break
            path = Path(fp)
            if not path.exists():
                continue
            if is_icloud_path(path):
                if await evict_file(path):
                    evicted += 1
            elif is_cloud_path(path):
                # Third-party providers (OneDrive/Google Drive/Dropbox) cannot
                # be evicted with brctl; count them so we can log once instead
                # of emitting a warning per file.
                skipped += 1

        if evicted:
            self.state.log(f"↑ Evicted {evicted} cloud files")
            logger.info("evict: evicted %d cloud files", evicted)
        if skipped:
            logger.info(
                "evict: skipped %d non-iCloud cloud files (brctl cannot evict "
                "OneDrive/Google Drive/Dropbox)",
                skipped,
            )

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
            scan_count = await self.scan()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # File hashes before anything can evict cloud files: hashing reads
            # each file in full, and an evicted file would be re-downloaded.
            hash_count = await self.process_file_hashes()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # Check if there are images needing AI (already indexed but no description)
            has_ai_work = False
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Image.id).where(
                        Image.ai_description.is_(None),
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

            await self.process_geocoding()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            await self.process_gps_inheritance()
            if self._stop_event.is_set():
                self.state.phase = "idle"
                return

            # Grouping needs both phash (metadata phase) and file_hash above.
            # Resolved groups are preserved by group_duplicates() itself.
            # Skip it entirely when nothing this run could have changed the
            # result: no new/updated images, no metadata (phash) computed, no
            # new file hashes -- unless there are no groups yet at all, in
            # which case we must run at least once to produce them.
            from backend.db.models import DuplicateGroup
            async with self.session_factory() as session:
                result = await session.execute(select(DuplicateGroup.id).limit(1))
                has_existing_groups = result.scalar_one_or_none() is not None

            should_group = (
                bool(scan_count)
                or has_metadata_work
                or bool(hash_count)
                or not has_existing_groups
            )

            if should_group:
                await self.group_duplicates()
                if self._stop_event.is_set():
                    self.state.phase = "idle"
                    return
            else:
                logger.info(
                    "run_full: skipping duplicate grouping - nothing changed "
                    "since last run (no scan changes, no metadata work, no "
                    "new hashes, and groups already exist)"
                )

            # Evict cloud files after all processing is done
            await self._evict_cloud_files()

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
