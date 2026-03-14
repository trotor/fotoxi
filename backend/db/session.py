from __future__ import annotations

import asyncio
from typing import Tuple

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.db.models import Base


def init_db(conn: AsyncConnection) -> None:
    """
    Synchronous-style helper (called via run_sync) that creates the FTS5
    virtual table for full-text search over the images table.
    """
    conn.exec_driver_sql(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS images_fts
        USING fts5(
            ai_description,
            ai_tags,
            file_name,
            content='images',
            content_rowid='id'
        )
        """
    )


async def create_engine_and_init(
    db_path: str,
) -> Tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """
    Create an async SQLAlchemy engine for the given SQLite path, initialise all
    ORM tables, create the FTS5 virtual table, and return the engine together
    with a bound session factory.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file, e.g. ``"/tmp/fotoxi.db"``.
        Pass ``":memory:"`` for an in-memory database.
    """
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        # Create all ORM-declared tables
        await conn.run_sync(Base.metadata.create_all)
        # Create FTS5 virtual table
        await conn.run_sync(init_db)

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )

    return engine, session_factory
