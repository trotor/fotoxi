"""App factory for Fotoxi FastAPI application."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import Config
from backend.db.session import create_engine_and_init
from backend.indexer.orchestrator import IndexerOrchestrator


async def create_app(config: Optional[Config] = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    config:
        Application configuration. If None, uses default Config().

    Returns
    -------
    Configured FastAPI application instance.
    """
    if config is None:
        config = Config()

    config.ensure_dirs()

    engine, session_factory = await create_engine_and_init(config.db_path)

    # Run Alembic migrations automatically on startup
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command
        import os
        alembic_ini = Path(__file__).parent.parent / "alembic.ini"
        if alembic_ini.exists():
            alembic_cfg = AlembicConfig(str(alembic_ini))
            # Temporarily change to project root for alembic to find script_location
            old_cwd = os.getcwd()
            os.chdir(str(alembic_ini.parent))
            command.upgrade(alembic_cfg, "head")
            os.chdir(old_cwd)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Alembic migration skipped: %s", exc)

    # Load persisted settings from DB
    await _load_persisted_settings(config, session_factory)

    # WebSocket connections list
    ws_connections: list = []

    def on_progress(state: Dict[str, Any]) -> None:
        """Broadcast progress updates to all connected WebSocket clients."""
        import asyncio

        message = json.dumps(state)
        dead: list = []
        for ws in list(ws_connections):
            try:
                # Schedule the coroutine on the running event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(ws.send_text(message))
                else:
                    loop.run_until_complete(ws.send_text(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                ws_connections.remove(ws)
            except ValueError:
                pass

    orchestrator = IndexerOrchestrator(
        config=config,
        session_factory=session_factory,
        on_progress=on_progress,
    )

    app = FastAPI(title="Fotoxi", version="0.3.4")

    # Store state on the app
    app.state.config = config
    app.state.session_factory = session_factory
    app.state.orchestrator = orchestrator
    app.state.ws_connections = ws_connections
    app.state.engine = engine

    # Pre-pull Ollama model in background
    async def _pull_ollama_model():
        import httpx
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{config.ollama_url}/api/pull",
                    json={"name": config.ollama_model, "stream": False},
                )
                if resp.status_code == 200:
                    import logging
                    logging.getLogger(__name__).info("Ollama model '%s' ready", config.ollama_model)
        except Exception:
            pass  # Ollama not running, ignore

    import asyncio as _asyncio
    _asyncio.create_task(_pull_ollama_model())

    # Auto-start metadata processing if enabled
    if config.auto_process_on_start:
        async def _auto_process():
            import logging as _log
            _log.getLogger(__name__).info("Auto-starting metadata processing...")
            await asyncio.sleep(2)  # Let server start first
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
                import logging as _log2
                _log2.getLogger(__name__).error("Auto-process error: %s", exc)
                orchestrator.state.phase = "error"
            finally:
                orchestrator.state.running = False
                orchestrator._notify()

        _asyncio.create_task(_auto_process())

    # Include routers
    from backend.api.routes import router
    from backend.api.websocket import ws_router

    app.include_router(router, prefix="/api")
    app.include_router(ws_router, prefix="/api")

    # Serve frontend SPA with fallback to index.html for client-side routing
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        from starlette.responses import FileResponse as StarletteFileResponse

        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return StarletteFileResponse(str(file_path))
            return StarletteFileResponse(str(frontend_dist / "index.html"))

    return app


async def _load_persisted_settings(config: Config, session_factory) -> None:
    """Load settings from the DB settings table into config on startup."""
    from sqlalchemy import select
    from backend.db.models import Setting

    async with session_factory() as session:
        result = await session.execute(select(Setting))
        rows = result.scalars().all()
        for row in rows:
            try:
                value = json.loads(row.value)
                if hasattr(config, row.key):
                    setattr(config, row.key, value)
            except (json.JSONDecodeError, TypeError):
                pass
