"""Tests for IndexerOrchestrator."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest
from PIL import Image as PilImage
from sqlalchemy import select

from backend.config import Config
from backend.db.models import Image
from backend.db.session import create_engine_and_init
from backend.indexer.orchestrator import IndexerOrchestrator, IndexerState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(path: Path, size: tuple = (100, 100)) -> None:
    """Write a minimal JPEG file at *path*."""
    img = PilImage.new("RGB", size, color=(128, 64, 32))
    img.save(path, format="JPEG")


async def _make_session_factory(tmp_path: Path):
    """Create an in-memory (or tmp file) SQLite engine and return the session factory."""
    db_path = str(tmp_path / "test.db")
    _engine, session_factory = await create_engine_and_init(db_path)
    return session_factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_phase(tmp_path):
    """scan() should discover 3 JPEG files and insert them as status='pending'."""
    # Create 3 JPEG files in a temp directory
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        _make_jpeg(images_dir / name)

    # Config pointing at our temp dir
    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=2,
    )

    session_factory = await _make_session_factory(tmp_path)
    orchestrator = IndexerOrchestrator(config, session_factory)

    await orchestrator.scan()

    # Verify 3 pending images in the DB
    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.status == "pending"))
        images = result.scalars().all()

    assert len(images) == 3
    file_names = {img.file_name for img in images}
    assert file_names == {"a.jpg", "b.jpg", "c.jpg"}
    for img in images:
        assert img.status == "pending"
        assert img.file_size > 0


@pytest.mark.asyncio
async def test_scan_phase_state_updates(tmp_path):
    """scan() should update IndexerState and call on_progress."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    for name in ("x.jpg", "y.jpg"):
        _make_jpeg(images_dir / name)

    config = Config(source_dirs=[str(images_dir)], thumbs_dir=str(tmp_path / "thumbs"))
    session_factory = await _make_session_factory(tmp_path)

    progress_calls: List[dict] = []
    orchestrator = IndexerOrchestrator(
        config, session_factory, on_progress=lambda s: progress_calls.append(s)
    )

    await orchestrator.scan()

    assert len(progress_calls) > 0
    final = progress_calls[-1]
    assert final["phase"] == "scanning"
    assert final["processed"] == 2


@pytest.mark.asyncio
async def test_scan_marks_missing_files(tmp_path):
    """scan() should mark DB entries as 'missing' when the file is gone from disk."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    jpg = images_dir / "gone.jpg"
    _make_jpeg(jpg)

    config = Config(source_dirs=[str(images_dir)], thumbs_dir=str(tmp_path / "thumbs"))
    session_factory = await _make_session_factory(tmp_path)

    # First scan – file exists
    orchestrator = IndexerOrchestrator(config, session_factory)
    await orchestrator.scan()

    # Remove the file
    jpg.unlink()

    # Second scan – file is gone
    orchestrator2 = IndexerOrchestrator(config, session_factory)
    await orchestrator2.scan()

    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.file_name == "gone.jpg"))
        img = result.scalar_one_or_none()

    assert img is not None
    assert img.status == "missing"


@pytest.mark.asyncio
async def test_metadata_phase(tmp_path):
    """scan + process_metadata should populate phash, dhash, width, and height."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    for name in ("p1.jpg", "p2.jpg"):
        _make_jpeg(images_dir / name, size=(80, 60))

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=2,
    )
    session_factory = await _make_session_factory(tmp_path)
    orchestrator = IndexerOrchestrator(config, session_factory)

    await orchestrator.scan()
    await orchestrator.process_metadata()

    async with session_factory() as session:
        result = await session.execute(select(Image))
        images = result.scalars().all()

    assert len(images) == 2
    for img in images:
        assert img.phash is not None, f"phash missing for {img.file_name}"
        assert img.dhash is not None, f"dhash missing for {img.file_name}"
        assert img.width is not None, f"width missing for {img.file_name}"
        assert img.height is not None, f"height missing for {img.file_name}"
        assert img.width > 0
        assert img.height > 0


@pytest.mark.asyncio
async def test_metadata_phase_generates_thumbnails(tmp_path):
    """process_metadata should create thumbnail files in thumbs_dir."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    _make_jpeg(images_dir / "thumb_test.jpg")

    thumbs_dir = tmp_path / "thumbs"
    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(thumbs_dir),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)
    orchestrator = IndexerOrchestrator(config, session_factory)

    await orchestrator.scan()
    await orchestrator.process_metadata()

    async with session_factory() as session:
        result = await session.execute(select(Image))
        img = result.scalars().first()

    assert img is not None
    thumb_path = thumbs_dir / f"{img.id}.jpg"
    assert thumb_path.exists(), f"Thumbnail not found at {thumb_path}"


@pytest.mark.asyncio
async def test_indexer_state_to_dict():
    """IndexerState.to_dict() should return a dict with all expected keys."""
    state = IndexerState(running=True, phase="scanning", total=10, processed=5, errors=1, speed=2.5)
    d = state.to_dict()
    assert d["running"] is True
    assert d["phase"] == "scanning"
    assert d["total"] == 10
    assert d["processed"] == 5
    assert d["errors"] == 1
    assert d["speed"] == 2.5
    assert "ai_total" in d
    assert "ai_processed" in d
    assert "recent_log" in d


@pytest.mark.asyncio
async def test_request_stop(tmp_path):
    """request_stop() should set _stop_event and halt the run_full pipeline."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    for i in range(5):
        _make_jpeg(images_dir / f"img{i}.jpg")

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)
    orchestrator = IndexerOrchestrator(config, session_factory)

    # Request stop immediately
    orchestrator.request_stop()
    await orchestrator.run_full()

    # running should be False after completion
    assert orchestrator.state.running is False


@pytest.mark.asyncio
async def test_scan_re_indexes_changed_files(tmp_path):
    """scan() should set status='pending' if a file's mtime or size changes."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    jpg = images_dir / "change.jpg"
    _make_jpeg(jpg)

    config = Config(source_dirs=[str(images_dir)], thumbs_dir=str(tmp_path / "thumbs"))
    session_factory = await _make_session_factory(tmp_path)

    # First scan
    orchestrator = IndexerOrchestrator(config, session_factory)
    await orchestrator.scan()

    # Manually mark as indexed to simulate a completed index
    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.file_name == "change.jpg"))
        img = result.scalar_one()
        img.status = "indexed"
        await session.commit()

    # Overwrite the file with a different image (changes size/mtime)
    _make_jpeg(jpg, size=(200, 200))
    # Touch to ensure mtime changes
    import time
    time.sleep(0.01)
    jpg.touch()

    # Second scan
    orchestrator2 = IndexerOrchestrator(config, session_factory)
    await orchestrator2.scan()

    async with session_factory() as session:
        result = await session.execute(select(Image).where(Image.file_name == "change.jpg"))
        img = result.scalar_one()

    assert img.status == "pending"
