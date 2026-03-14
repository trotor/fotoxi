"""Fotoxi entry point: creates the FastAPI app and runs the uvicorn server."""
from __future__ import annotations

import asyncio

import uvicorn
from fastapi import FastAPI

from backend.config import Config


def create_app(config: Config | None = None) -> FastAPI:
    if config is None:
        config = Config()

    config.ensure_dirs()

    app = FastAPI(title="Fotoxi", version="0.1.0")
    app.state.config = config

    return app


async def main() -> None:
    config = Config()
    app = create_app(config)

    server_config = uvicorn.Config(
        app,
        host=config.server_host,
        port=config.server_port,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
