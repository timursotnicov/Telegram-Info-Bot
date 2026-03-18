"""Pytest fixtures for SaveBot tests."""
import asyncio
import pytest
import aiosqlite
from unittest.mock import AsyncMock, MagicMock


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


# ── aiogram mock factories ────────────────────────────────

def make_callback(user_id, callback_data, reply_markup=None):
    """Factory for mocked aiogram CallbackQuery."""
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.data = callback_data
    cb.message = AsyncMock()
    cb.message.reply_markup = reply_markup
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.message.bot = MagicMock()
    return cb


def make_message(user_id, text="", bot_db=None):
    """Factory for mocked aiogram Message."""
    msg = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.text = text
    msg.reply = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.get = MagicMock(return_value=bot_db)
    return msg
