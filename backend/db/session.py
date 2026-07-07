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


# Columns indexed by the FTS5 table. Includes the generic AI columns plus the
# per-language columns so full-text search matches regardless of the language
# the AI analysis ran in.
_FTS_COLUMNS = (
    "ai_description",
    "ai_tags",
    "file_name",
    "ai_description_en",
    "ai_tags_en",
    "ai_description_fi",
    "ai_tags_fi",
)


def init_db(conn: AsyncConnection) -> None:
    """
    Synchronous-style helper (called via run_sync) that creates/maintains the
    FTS5 virtual table and the triggers that keep it in sync with ``images``.

    The index covers every column in ``_FTS_COLUMNS``. If an existing
    ``images_fts`` was created with an older, narrower column set, it is dropped
    and recreated so pre-existing databases pick up the new columns on startup.
    """
    existing_cols = {
        row[1] for row in conn.exec_driver_sql("PRAGMA table_info(images_fts)").fetchall()
    }
    if existing_cols and set(_FTS_COLUMNS) - existing_cols:
        # Old/narrow schema — drop so it is recreated with the full column set.
        conn.exec_driver_sql("DROP TABLE IF EXISTS images_fts")

    cols = ",\n            ".join(_FTS_COLUMNS)
    conn.exec_driver_sql(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS images_fts
        USING fts5(
            {cols},
            content='images',
            content_rowid='id'
        )
        """
    )

    # (Re)create the sync triggers so they always match the current column set.
    col_names = ", ".join(_FTS_COLUMNS)
    new_vals = ", ".join(f"new.{c}" for c in _FTS_COLUMNS)
    old_vals = ", ".join(f"old.{c}" for c in _FTS_COLUMNS)
    update_of = ", ".join(_FTS_COLUMNS)

    for trg in ("images_ai_insert", "images_ai_delete", "images_ai_update"):
        conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trg}")

    conn.exec_driver_sql(
        f"""
        CREATE TRIGGER images_ai_insert AFTER INSERT ON images BEGIN
            INSERT INTO images_fts(rowid, {col_names})
            VALUES (new.id, {new_vals});
        END
        """
    )
    conn.exec_driver_sql(
        f"""
        CREATE TRIGGER images_ai_delete BEFORE DELETE ON images BEGIN
            INSERT INTO images_fts(images_fts, rowid, {col_names})
            VALUES ('delete', old.id, {old_vals});
        END
        """
    )
    conn.exec_driver_sql(
        f"""
        CREATE TRIGGER images_ai_update AFTER UPDATE OF {update_of} ON images BEGIN
            INSERT INTO images_fts(images_fts, rowid, {col_names})
            VALUES ('delete', old.id, {old_vals});
            INSERT INTO images_fts(rowid, {col_names})
            VALUES (new.id, {new_vals});
        END
        """
    )

    # Rebuild FTS index from current data (also populates the new columns).
    conn.exec_driver_sql("INSERT INTO images_fts(images_fts) VALUES('rebuild')")


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
    kwargs: dict = {"echo": False}
    if db_path != ":memory:":
        kwargs["pool_size"] = 20
        kwargs["max_overflow"] = 30
    engine = create_async_engine(url, **kwargs)

    async with engine.begin() as conn:
        # Create all ORM-declared tables
        await conn.run_sync(Base.metadata.create_all)
        # Create FTS5 virtual table
        await conn.run_sync(init_db)

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )

    return engine, session_factory
