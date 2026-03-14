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

    app = FastAPI(title="Fotoxi", version="0.1.0")

    # Store state on the app
    app.state.config = config
    app.state.session_factory = session_factory
    app.state.orchestrator = orchestrator
    app.state.ws_connections = ws_connections
    app.state.engine = engine

    # Include routers
    from backend.api.routes import router
    from backend.api.websocket import ws_router

    app.include_router(router, prefix="/api")
    app.include_router(ws_router, prefix="/api")

    # Mount frontend static files if directory exists
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")

    return app
