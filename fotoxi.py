"""Fotoxi entry point: creates the FastAPI app and runs the uvicorn server."""
from __future__ import annotations

import asyncio

import uvicorn


async def main() -> None:
    from backend.main import create_app

    app = await create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
