"""Fotoxi CLI - photo management and metadata database.

Usage:
    python fotoxi.py serve              Start web UI (default)
    python fotoxi.py add <folder>       Add source folder
    python fotoxi.py folders            List source folders
    python fotoxi.py remove <folder>    Remove source folder
    python fotoxi.py scan               Scan for new/changed files
    python fotoxi.py index              Run full indexing (scan + metadata + AI + duplicates)
    python fotoxi.py status             Show database status
    python fotoxi.py duplicates         Show duplicate groups summary
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from backend.main import create_app

    app = await create_app()
    port = args.port or 8001
    print(f"Starting Fotoxi at http://localhost:{port}")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def _get_session_and_config():
    from backend.config import Config
    from backend.db.session import create_engine_and_init

    config = Config()
    config.ensure_dirs()
    engine, session_factory = await create_engine_and_init(config.db_path)

    # Load persisted settings
    from sqlalchemy import select
    from backend.db.models import Setting
    import json

    async with session_factory() as session:
        result = await session.execute(select(Setting))
        for row in result.scalars().all():
            try:
                value = json.loads(row.value)
                if hasattr(config, row.key):
                    setattr(config, row.key, value)
            except (json.JSONDecodeError, TypeError):
                pass

    return engine, session_factory, config


async def _save_source_dirs(session_factory, source_dirs: list[str]) -> None:
    import json
    from sqlalchemy import select
    from backend.db.models import Setting

    async with session_factory() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "source_dirs")
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = json.dumps(source_dirs)
        else:
            session.add(Setting(key="source_dirs", value=json.dumps(source_dirs)))
        await session.commit()


async def cmd_add(args: argparse.Namespace) -> None:
    from pathlib import Path

    folder = str(Path(args.folder).expanduser().resolve())
    if not Path(folder).is_dir():
        print(f"Error: '{folder}' is not a directory")
        sys.exit(1)

    engine, session_factory, config = await _get_session_and_config()
    if folder in config.source_dirs:
        print(f"Already added: {folder}")
    else:
        config.source_dirs.append(folder)
        await _save_source_dirs(session_factory, config.source_dirs)
        print(f"Added: {folder}")
    print(f"Source folders ({len(config.source_dirs)}):")
    for d in config.source_dirs:
        print(f"  {d}")
    await engine.dispose()


async def cmd_folders(args: argparse.Namespace) -> None:
    engine, session_factory, config = await _get_session_and_config()
    if not config.source_dirs:
        print("No source folders configured.")
        print("Add one with: python fotoxi.py add <folder>")
    else:
        print(f"Source folders ({len(config.source_dirs)}):")
        for d in config.source_dirs:
            print(f"  {d}")
    await engine.dispose()


async def cmd_remove(args: argparse.Namespace) -> None:
    from pathlib import Path

    folder = str(Path(args.folder).expanduser().resolve())
    engine, session_factory, config = await _get_session_and_config()

    if folder in config.source_dirs:
        config.source_dirs.remove(folder)
        await _save_source_dirs(session_factory, config.source_dirs)
        print(f"Removed: {folder}")
    else:
        print(f"Not found: {folder}")
        print("Current folders:")
        for d in config.source_dirs:
            print(f"  {d}")
    await engine.dispose()


async def cmd_scan(args: argparse.Namespace) -> None:
    engine, session_factory, config = await _get_session_and_config()

    if not config.source_dirs:
        print("No source folders configured. Add one with: python fotoxi.py add <folder>")
        await engine.dispose()
        return

    from backend.indexer.orchestrator import IndexerOrchestrator

    def on_progress(state):
        phase = state["phase"]
        processed = state["processed"]
        total = state["total"]
        current = state.get("current_file", "")
        if total > 0:
            pct = round(processed / total * 100)
            print(f"\r  [{phase}] {processed}/{total} ({pct}%) {current}    ", end="", flush=True)

    orchestrator = IndexerOrchestrator(config, session_factory, on_progress=on_progress)
    print("Scanning source folders...")
    await orchestrator.scan()
    print(f"\nScan complete. Found {orchestrator.state.processed} files.")
    await engine.dispose()


async def cmd_index(args: argparse.Namespace) -> None:
    engine, session_factory, config = await _get_session_and_config()

    if not config.source_dirs:
        print("No source folders configured. Add one with: python fotoxi.py add <folder>")
        await engine.dispose()
        return

    from backend.indexer.orchestrator import IndexerOrchestrator

    last_phase = ""

    def on_progress(state):
        nonlocal last_phase
        phase = state["phase"]
        processed = state["processed"]
        total = state["total"]
        errors = state["errors"]
        current = state.get("current_file", "")
        speed = state.get("speed", 0)

        if phase != last_phase:
            if last_phase:
                print()  # newline after previous phase
            phase_labels = {
                "scanning": "Scanning files",
                "metadata": "Extracting metadata (EXIF, hashes, thumbnails)",
                "ai_analysis": "AI analysis (Ollama)",
                "grouping": "Finding duplicates",
                "complete": "Complete",
            }
            print(f"\n{phase_labels.get(phase, phase)}...")
            last_phase = phase

        if total > 0:
            pct = round(processed / total * 100)
            err_str = f" ({errors} errors)" if errors else ""
            spd_str = f" [{speed:.1f}/s]" if speed > 0 else ""
            print(f"\r  {processed}/{total} ({pct}%){err_str}{spd_str} {current[:50]}    ", end="", flush=True)

    orchestrator = IndexerOrchestrator(config, session_factory, on_progress=on_progress)

    print("Starting full indexing pipeline...")
    await orchestrator.run_full()
    print(f"\n\nDone! Phase: {orchestrator.state.phase}")
    await engine.dispose()


async def cmd_status(args: argparse.Namespace) -> None:
    from sqlalchemy import select, func
    from backend.db.models import Image, DuplicateGroup

    engine, session_factory, config = await _get_session_and_config()

    async with session_factory() as session:
        # Count by status
        result = await session.execute(
            select(Image.status, func.count(Image.id)).group_by(Image.status)
        )
        status_counts = dict(result.all())

        # Total
        total = sum(status_counts.values())

        # With EXIF
        result = await session.execute(
            select(func.count(Image.id)).where(Image.exif_date.is_not(None))
        )
        with_exif = result.scalar() or 0

        # With AI
        result = await session.execute(
            select(func.count(Image.id)).where(Image.ai_description.is_not(None))
        )
        with_ai = result.scalar() or 0

        # With GPS
        result = await session.execute(
            select(func.count(Image.id)).where(Image.exif_gps_lat.is_not(None))
        )
        with_gps = result.scalar() or 0

        # Duplicates
        result = await session.execute(select(func.count(DuplicateGroup.id)))
        dup_groups = result.scalar() or 0

        # Videos
        from backend.indexer.scanner import VIDEO_EXTENSIONS
        video_exts = [ext.upper().lstrip(".") for ext in VIDEO_EXTENSIONS]
        result = await session.execute(
            select(func.count(Image.id)).where(
                Image.format.in_(video_exts),
                Image.status.notin_(["missing", "error"]),
            )
        )
        videos = result.scalar() or 0

    active = total - status_counts.get('missing', 0) - status_counts.get('error', 0) - status_counts.get('rejected', 0)
    print("Fotoxi Database Status")
    print("=" * 40)
    print(f"Total files:         {total}")
    print(f"  Photos:            {active - videos}")
    print(f"  Videos:            {videos}")
    print()
    print("By status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:20s} {count}")

    print(f"With EXIF date:      {with_exif}")
    print(f"With GPS coords:     {with_gps}")
    print(f"With AI description: {with_ai}")
    print(f"Videos:              {videos}")
    print(f"Duplicate groups:    {dup_groups}")
    print()
    print(f"Source folders ({len(config.source_dirs)}):")
    for d in config.source_dirs:
        print(f"  {d}")
    print()
    print(f"Database: {config.db_path}")
    print(f"Thumbnails: {config.thumbs_dir}")

    await engine.dispose()


async def cmd_duplicates(args: argparse.Namespace) -> None:
    from sqlalchemy import select, func
    from backend.db.models import DuplicateGroup, DuplicateGroupMember, Image

    engine, session_factory, config = await _get_session_and_config()

    async with session_factory() as session:
        result = await session.execute(
            select(DuplicateGroup).order_by(DuplicateGroup.id)
        )
        groups = result.scalars().all()

        if not groups:
            print("No duplicate groups found.")
            await engine.dispose()
            return

        print(f"Duplicate groups: {len(groups)}")
        print("=" * 60)

        for g in groups[:20]:  # Show first 20
            result = await session.execute(
                select(DuplicateGroupMember).where(DuplicateGroupMember.group_id == g.id)
            )
            members = result.scalars().all()

            # Fetch images
            imgs = []
            for m in members:
                img_result = await session.execute(select(Image).where(Image.id == m.image_id))
                img = img_result.scalar_one_or_none()
                if img:
                    imgs.append((m, img))

            resolved = all(m.user_choice is not None for m, _ in imgs)
            status_str = "resolved" if resolved else "pending"

            print(f"\nGroup #{g.id} [{g.match_type}] ({len(imgs)} images) [{status_str}]")
            for m, img in imgs:
                choice = f" [{m.user_choice}]" if m.user_choice else ""
                size_mb = img.file_size / 1024 / 1024 if img.file_size else 0
                res = f"{img.width}x{img.height}" if img.width else "?"
                print(f"  {img.file_name:40s} {size_mb:6.1f} MB  {res:12s}{choice}")

        if len(groups) > 20:
            print(f"\n... and {len(groups) - 20} more groups. Use web UI for full view.")

    await engine.dispose()


async def cmd_rebuild_thumbs(args: argparse.Namespace) -> None:
    from sqlalchemy import select
    from backend.db.models import Image
    from backend.indexer.thumbnailer import generate_thumbnail
    from backend.indexer.eviction import evict_file, is_cloud_path

    engine, session_factory, config = await _get_session_and_config()
    thumbs_dir = Path(config.thumbs_dir)

    async with session_factory() as session:
        result = await session.execute(
            select(Image).where(Image.status.notin_(["missing", "error"]))
        )
        images = result.scalars().all()

    total = len(images)
    print(f"Rebuilding thumbnails for {total} images (with EXIF orientation fix)...")

    done = 0
    errors = 0
    evicted = 0
    for img in images:
        path = Path(img.file_path)
        if path.exists():
            result = generate_thumbnail(path, thumbs_dir, img.id)
            if result:
                done += 1
                # Evict cloud files back to cloud after thumbnail is generated
                if is_cloud_path(path):
                    await evict_file(path)
                    evicted += 1
            else:
                errors += 1
        else:
            errors += 1
        if (done + errors) % 100 == 0:
            print(f"\r  {done + errors}/{total} ({done} ok, {errors} errors)", end="", flush=True)

    print(f"\nDone! {done} thumbnails rebuilt, {errors} errors, {evicted} cloud files evicted.")
    await engine.dispose()


async def cmd_ai(args: argparse.Namespace) -> None:
    from sqlalchemy import select, func, update
    from backend.db.models import Image
    from backend.indexer.analyzer import analyze_image
    from backend.indexer.ai_thumbs import generate_ai_thumb
    import time as _time

    engine, session_factory, config = await _get_session_and_config()

    # If --reset, clear all AI descriptions
    if getattr(args, 'reset', False):
        async with session_factory() as session:
            await session.execute(
                update(Image).where(Image.ai_description.is_not(None)).values(
                    ai_description=None, ai_tags=None,
                    ai_description_en=None, ai_tags_en=None,
                    ai_description_fi=None, ai_tags_fi=None,
                    ai_quality_score=None, ai_model=None,
                )
            )
            await session.commit()
        print("Cleared all AI descriptions (all languages). Run again without --reset to regenerate.")
        await engine.dispose()
        return

    # Override lang/model from args
    lang = getattr(args, 'lang', None) or config.ai_language
    model = getattr(args, 'model', None) or config.ollama_model
    # Normalize language
    if lang in ("en", "english"): lang = "english"
    elif lang in ("fi", "finnish"): lang = "finnish"

    # Find images needing AI for this language
    from backend.indexer.scanner import VIDEO_EXTENSIONS
    video_exts = [ext.upper().lstrip(".") for ext in VIDEO_EXTENSIONS]

    # Pick the right column to check
    lang_col = Image.ai_description_en if lang == "english" else Image.ai_description_fi if lang == "finnish" else Image.ai_description

    async with session_factory() as session:
        result = await session.execute(
            select(Image).where(
                lang_col.is_(None),
                Image.phash.is_not(None),
                Image.status.in_(["indexed", "kept"]),
                Image.format.notin_(video_exts),
            ).order_by(Image.file_size)
        )
        images = result.scalars().all()

    total = len(images)
    if total == 0:
        print(f"All images already have AI descriptions ({lang}).")
        await engine.dispose()
        return

    print(f"AI analysis: {total} images, model={model}, lang={lang}")
    print(f"Using thumbnails (300px) for speed. Ctrl+C to stop (progress saved).")

    done = 0
    errors = 0
    t0 = _time.time()
    thumbs_dir = Path(config.thumbs_dir)

    for img in images:
        thumb = thumbs_dir / f"{img.id}.jpg"
        if not thumb.exists():
            errors += 1
            continue

        try:
            result = analyze_image(
                path=Path(img.file_path),
                ollama_url=config.ollama_url,
                model=model,
                language=lang,
                quality_enabled=config.ai_quality_enabled,
                thumb_path=thumb,
                retries=1,
                retry_delay=2.0,
            )

            if result:
                import json as _json
                import datetime as _dt
                async with session_factory() as session:
                    db_img = (await session.execute(select(Image).where(Image.id == img.id))).scalar_one_or_none()
                    if db_img:
                        desc = result["description"]
                        tags_json = _json.dumps(result["tags"])
                        db_img.ai_description = desc
                        db_img.ai_tags = tags_json
                        if lang == "english":
                            db_img.ai_description_en = desc
                            db_img.ai_tags_en = tags_json
                        elif lang == "finnish":
                            db_img.ai_description_fi = desc
                            db_img.ai_tags_fi = tags_json
                        colors = result.get("colors", [])
                        db_img.ai_colors = _json.dumps(colors) if colors else None
                        db_img.ai_scene_type = result.get("scene_type")
                        db_img.ai_quality_score = result.get("quality_score")
                        db_img.ai_model = model
                        db_img.indexed_at = _dt.datetime.now(_dt.timezone.utc)
                        await session.commit()
                        # Update FTS index
                        from sqlalchemy import text
                        await session.execute(text(
                            "INSERT OR REPLACE INTO images_fts(rowid, ai_description, ai_tags, file_name) "
                            "VALUES (:id, :desc, :tags, :name)"
                        ), {"id": img.id, "desc": desc, "tags": tags_json, "name": img.file_name})
                        await session.commit()
                done += 1
            else:
                errors += 1

        except KeyboardInterrupt:
            print(f"\nStopped. {done}/{total} done, {errors} errors.")
            break
        except Exception as e:
            errors += 1

        elapsed = _time.time() - t0
        speed = done / elapsed if elapsed > 0 else 0
        eta = (total - done - errors) / speed if speed > 0 else 0
        eta_str = f"{eta/60:.0f}min" if eta < 3600 else f"{eta/3600:.1f}h"
        print(f"\r  {done+errors}/{total} ({done} ok, {errors} err) {speed:.2f}/s ~{eta_str}  {img.file_name[:40]}", end="", flush=True)

    print(f"\nDone! {done} AI descriptions created, {errors} errors.")
    await engine.dispose()


def cmd_backup(args: argparse.Namespace) -> None:
    import shutil
    from datetime import datetime
    from backend.config import Config

    config = Config()
    db_path = config.db_path
    if not Path(db_path).exists():
        print(f"No database found at {db_path}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    size_mb = Path(backup_path).stat().st_size / 1024 / 1024
    print(f"Backup created: {backup_path} ({size_mb:.1f} MB)")


def cmd_migrate(args: argparse.Namespace) -> None:
    from alembic.config import Config as AlembicConfig
    from alembic import command

    alembic_cfg = AlembicConfig("alembic.ini")
    print("Running database migrations...")
    command.upgrade(alembic_cfg, "head")
    print("Migrations complete.")


def main():
    parser = argparse.ArgumentParser(
        prog="fotoxi",
        description="Fotoxi - Photo management and metadata database",
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_p = subparsers.add_parser("serve", help="Start web UI server")
    serve_p.add_argument("-p", "--port", type=int, default=8001, help="Port (default 8001)")

    # add
    add_p = subparsers.add_parser("add", help="Add a source folder")
    add_p.add_argument("folder", help="Path to folder")

    # folders
    subparsers.add_parser("folders", help="List source folders")

    # remove
    rm_p = subparsers.add_parser("remove", help="Remove a source folder")
    rm_p.add_argument("folder", help="Path to folder")

    # scan
    subparsers.add_parser("scan", help="Scan for new/changed files")

    # index
    subparsers.add_parser("index", help="Run full indexing pipeline")

    # status
    subparsers.add_parser("status", help="Show database status")

    # duplicates
    subparsers.add_parser("duplicates", help="Show duplicate groups")

    # backup
    subparsers.add_parser("backup", help="Create database backup")

    # migrate
    subparsers.add_parser("migrate", help="Run database migrations")

    # rebuild-thumbs
    subparsers.add_parser("rebuild-thumbs", help="Rebuild all thumbnails (fixes orientation)")

    # ai
    ai_p = subparsers.add_parser("ai", help="Run AI descriptions (uses thumbnails, skips videos)")
    ai_p.add_argument("--reset", action="store_true", help="Clear all AI descriptions first")
    ai_p.add_argument("--lang", choices=["en", "fi"], help="Override language (default: from settings)")
    ai_p.add_argument("--model", help="Override Ollama model (default: from settings)")

    args = parser.parse_args()

    if args.command is None:
        # Default: serve
        args.port = 8001
        asyncio.run(cmd_serve(args))
    elif args.command == "serve":
        asyncio.run(cmd_serve(args))
    elif args.command == "add":
        asyncio.run(cmd_add(args))
    elif args.command == "folders":
        asyncio.run(cmd_folders(args))
    elif args.command == "remove":
        asyncio.run(cmd_remove(args))
    elif args.command == "scan":
        asyncio.run(cmd_scan(args))
    elif args.command == "index":
        asyncio.run(cmd_index(args))
    elif args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "duplicates":
        asyncio.run(cmd_duplicates(args))
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "migrate":
        cmd_migrate(args)
    elif args.command == "rebuild-thumbs":
        asyncio.run(cmd_rebuild_thumbs(args))
    elif args.command == "ai":
        asyncio.run(cmd_ai(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
