"""Pytest fixtures for SaveBot tests."""
import asyncio
import pytest
import aiosqlite


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db():
    """In-memory SQLite database with full schema."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row

    from savebot.db.models import SCHEMA
    await conn.executescript(SCHEMA)
    await conn.commit()

    # Apply migrations
    from savebot.db.migrations import run_migrations
    await run_migrations(conn)

    yield conn
    await conn.close()
