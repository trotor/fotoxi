"""Tests for IndexerOrchestrator."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import List

import pytest
from PIL import Image as PilImage
from sqlalchemy import select

from backend.config import Config
from backend.db.models import DuplicateGroup, Image
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


@pytest.mark.asyncio
async def test_run_full_includes_hashing_and_grouping(tmp_path, monkeypatch):
    """run_full() hashes before eviction and groups duplicates after metadata."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)

    # Give run_full() both metadata work and AI work so neither branch is skipped.
    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/pending.jpg", file_name="pending.jpg", file_size=10,
                file_mtime=1.0, status="pending",
            )
        )
        session.add(
            Image(
                file_path="/p/indexed.jpg", file_name="indexed.jpg", file_size=10,
                file_mtime=2.0, status="indexed", ai_description=None,
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)

    calls: List[str] = []

    def _recorder(name: str):
        async def _fn(*args, **kwargs):
            calls.append(name)
        return _fn

    for name in (
        "scan", "process_file_hashes", "process_metadata", "process_ai",
        "process_geocoding", "process_gps_inheritance", "group_duplicates",
        "_evict_cloud_files",
    ):
        monkeypatch.setattr(orchestrator, name, _recorder(name))

    await orchestrator.run_full()

    assert "process_file_hashes" in calls
    assert "group_duplicates" in calls
    # Hashing reads whole files, so it must precede cloud eviction.
    assert calls.index("scan") < calls.index("process_file_hashes")
    assert calls.index("process_file_hashes") < calls.index("_evict_cloud_files")
    # Grouping needs phash from the metadata phase, and must precede eviction.
    assert calls.index("process_metadata") < calls.index("group_duplicates")
    assert calls.index("group_duplicates") < calls.index("_evict_cloud_files")
    assert orchestrator.state.running is False
    assert orchestrator.state.phase == "complete"


@pytest.mark.asyncio
async def test_run_full_stop_skips_grouping_and_eviction(tmp_path, monkeypatch):
    """A stop requested mid-pipeline skips the remaining phases."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/pending.jpg", file_name="pending.jpg", file_size=10,
                file_mtime=1.0, status="pending",
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)

    calls: List[str] = []

    def _recorder(name: str):
        async def _fn(*args, **kwargs):
            calls.append(name)
        return _fn

    for name in (
        "scan", "process_file_hashes", "process_ai", "process_geocoding",
        "process_gps_inheritance", "group_duplicates", "_evict_cloud_files",
    ):
        monkeypatch.setattr(orchestrator, name, _recorder(name))

    # Metadata phase asks to stop; everything after it must be skipped.
    async def _metadata_then_stop(*args, **kwargs):
        calls.append("process_metadata")
        orchestrator.request_stop()

    monkeypatch.setattr(orchestrator, "process_metadata", _metadata_then_stop)

    await orchestrator.run_full()

    assert "process_metadata" in calls
    assert "group_duplicates" not in calls
    assert "_evict_cloud_files" not in calls
    assert orchestrator.state.running is False
    assert orchestrator.state.phase == "idle"


@pytest.mark.asyncio
async def test_process_file_hashes_is_noop_when_all_hashed(tmp_path):
    """process_file_hashes() does no work when every image already has a hash."""
    config = Config(
        source_dirs=[str(tmp_path / "photos")],
        thumbs_dir=str(tmp_path / "thumbs"),
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/done.jpg", file_name="done.jpg", file_size=10,
                file_mtime=1.0, status="indexed", file_hash="abc123",
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)
    orchestrator.state.total = 0
    await orchestrator.process_file_hashes()

    # Early return leaves the counters untouched — nothing was queued for hashing.
    assert orchestrator.state.total == 0
    assert orchestrator.state.processed == 0


# ---------------------------------------------------------------------------
# 0.4.15: skip grouping when nothing changed, and get grouping off the loop
# ---------------------------------------------------------------------------


def _no_op_recorder(calls: List[str], name: str, return_value=None):
    async def _fn(*args, **kwargs):
        calls.append(name)
        return return_value
    return _fn


@pytest.mark.asyncio
async def test_run_full_skips_grouping_when_nothing_changed(tmp_path, monkeypatch):
    """No scan changes, no metadata work, no new hashes, and a group already
    exists -> run_full() must not re-run group_duplicates()."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        # Fully processed already: not pending (no metadata work), has both
        # hashes, and already has an AI description (no AI work either).
        session.add(
            Image(
                file_path="/p/indexed.jpg", file_name="indexed.jpg", file_size=10,
                file_mtime=1.0, status="indexed", phash="abc", file_hash="def",
                ai_description="already described",
            )
        )
        # A duplicate group already exists from a previous run.
        session.add(DuplicateGroup(match_type="phash"))
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)
    calls: List[str] = []

    monkeypatch.setattr(orchestrator, "scan", _no_op_recorder(calls, "scan", 0))
    monkeypatch.setattr(
        orchestrator, "process_file_hashes", _no_op_recorder(calls, "process_file_hashes", 0)
    )
    for name in (
        "process_metadata", "process_ai", "process_geocoding",
        "process_gps_inheritance", "group_duplicates", "_evict_cloud_files",
    ):
        monkeypatch.setattr(orchestrator, name, _no_op_recorder(calls, name))

    await orchestrator.run_full()

    assert "group_duplicates" not in calls
    # The rest of the pipeline still runs.
    assert "_evict_cloud_files" in calls
    assert orchestrator.state.phase == "complete"


@pytest.mark.asyncio
async def test_run_full_still_groups_when_no_groups_exist_yet(tmp_path, monkeypatch):
    """Same 'nothing changed' situation as above, but duplicate_groups is
    empty -> run_full() must still run group_duplicates() at least once."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()

    config = Config(
        source_dirs=[str(images_dir)],
        thumbs_dir=str(tmp_path / "thumbs"),
        thread_pool_size=1,
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/indexed.jpg", file_name="indexed.jpg", file_size=10,
                file_mtime=1.0, status="indexed", phash="abc", file_hash="def",
                ai_description="already described",
            )
        )
        # No DuplicateGroup rows at all yet.
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)
    calls: List[str] = []

    monkeypatch.setattr(orchestrator, "scan", _no_op_recorder(calls, "scan", 0))
    monkeypatch.setattr(
        orchestrator, "process_file_hashes", _no_op_recorder(calls, "process_file_hashes", 0)
    )
    for name in (
        "process_metadata", "process_ai", "process_geocoding",
        "process_gps_inheritance", "group_duplicates", "_evict_cloud_files",
    ):
        monkeypatch.setattr(orchestrator, name, _no_op_recorder(calls, name))

    await orchestrator.run_full()

    assert "group_duplicates" in calls


@pytest.mark.asyncio
async def test_scan_returns_change_count(tmp_path):
    """scan() returns the number of rows it created/updated, and 0 when a
    re-scan finds nothing new."""
    images_dir = tmp_path / "photos"
    images_dir.mkdir()
    for name in ("a.jpg", "b.jpg"):
        _make_jpeg(images_dir / name)

    config = Config(source_dirs=[str(images_dir)], thumbs_dir=str(tmp_path / "thumbs"))
    session_factory = await _make_session_factory(tmp_path)

    orchestrator = IndexerOrchestrator(config, session_factory)
    count = await orchestrator.scan()
    assert count == 2

    # Re-scan: nothing changed on disk, so nothing should be reported changed.
    orchestrator2 = IndexerOrchestrator(config, session_factory)
    count2 = await orchestrator2.scan()
    assert count2 == 0


@pytest.mark.asyncio
async def test_group_duplicates_runs_find_duplicate_groups_off_event_loop(tmp_path, monkeypatch):
    """find_duplicate_groups() must be dispatched to the thread pool, not
    called directly on the event loop (which would freeze the whole app)."""
    import backend.indexer.orchestrator as orch_mod

    config = Config(
        source_dirs=[str(tmp_path / "photos")],
        thumbs_dir=str(tmp_path / "thumbs"),
    )
    session_factory = await _make_session_factory(tmp_path)

    async with session_factory() as session:
        session.add(
            Image(
                file_path="/p/a.jpg", file_name="a.jpg", file_size=1, file_mtime=1.0,
                status="indexed", phash="0000000000000000",
            )
        )
        session.add(
            Image(
                file_path="/p/b.jpg", file_name="b.jpg", file_size=1, file_mtime=1.0,
                status="indexed", phash="0000000000000000",
            )
        )
        await session.commit()

    orchestrator = IndexerOrchestrator(config, session_factory)

    seen_threads: List[threading.Thread] = []
    original = orch_mod.find_duplicate_groups

    def _spy(*args, **kwargs):
        seen_threads.append(threading.current_thread())
        return original(*args, **kwargs)

    monkeypatch.setattr(orch_mod, "find_duplicate_groups", _spy)

    await orchestrator.group_duplicates()

    assert len(seen_threads) == 1, "find_duplicate_groups should be called exactly once"
    assert seen_threads[0] is not threading.main_thread(), (
        "find_duplicate_groups ran on the main/event-loop thread instead of "
        "being dispatched to the executor"
    )
