"""Tests for savebot.services.digest — generation functions only."""
import pytest
from savebot.db import queries
from savebot.services.digest import generate_weekly_digest, generate_daily_brief

USER_ID = 1


# ── Weekly Digest ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_weekly_digest_with_items(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Work", "💼")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Weekly task report",
        tags=["work"], ai_summary="Weekly task report",
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Meeting notes from Monday",
        tags=["meetings"], ai_summary="Meeting notes from Monday",
    )

    result = await generate_weekly_digest(db, USER_ID)
    assert result is not None
    assert "Недельный дайджест" in result
    assert "Сохранено за неделю" in result
    assert "Итого" in result
    assert "Work" in result


@pytest.mark.asyncio
async def test_weekly_digest_empty_week(db):
    # No items at all => should return None
    result = await generate_weekly_digest(db, USER_ID)
    assert result is None


# ── Daily Brief ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_brief_with_sections(db):
    # Create Inbox category and items so inbox section is populated
    inbox = await queries.get_or_create_inbox_category(db, USER_ID)
    await queries.save_item(
        db, USER_ID, category_id=inbox["id"],
        content_type="text", content_text="Inbox item 1",
        tags=["inbox"],
    )
    # Create a regular category and recent items (for "yesterday" section)
    cat = await queries.get_or_create_category(db, USER_ID, "Dev", "💻")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Fresh code review notes",
        tags=["code"], ai_summary="Fresh code review notes",
    )

    # Insert a forgotten item (>30 days old, not pinned)
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, is_pinned, created_at)
           VALUES (?, 'text', 'Old forgotten thing', ?, 0, datetime('now', '-60 days'))""",
        (cat["id"], USER_ID),
    )
    await db.commit()

    result = await generate_daily_brief(db, USER_ID)
    assert result is not None
    assert "Daily Brief" in result


@pytest.mark.asyncio
async def test_daily_brief_empty_db(db):
    result = await generate_daily_brief(db, USER_ID)
    assert result is None
