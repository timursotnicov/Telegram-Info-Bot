"""Tests for savebot.services.connections."""
import pytest
from savebot.db import queries
from savebot.services.connections import find_related_items

USER_ID = 1


async def _seed_items(db):
    """Create a category and several items for connection tests."""
    cat = await queries.get_or_create_category(db, USER_ID, "Dev", "💻")
    cat2 = await queries.get_or_create_category(db, USER_ID, "Design", "🎨")

    item_a = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Python async patterns guide",
        tags=["python", "async"], ai_summary="Python async patterns guide",
    )
    item_b = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Async Python concurrency deep dive",
        tags=["python", "async"], ai_summary="Async Python concurrency deep dive",
    )
    item_c = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Django deployment checklist",
        tags=["django", "deploy"], ai_summary="Django deployment checklist",
    )
    item_d = await queries.save_item(
        db, USER_ID, category_id=cat2["id"],
        content_type="text", content_text="Figma tips for developers",
        tags=["figma", "design"], ai_summary="Figma tips for developers",
    )
    return cat, cat2, item_a, item_b, item_c, item_d


@pytest.mark.asyncio
async def test_shared_tags_found(db):
    cat, cat2, item_a, item_b, item_c, item_d = await _seed_items(db)
    related = await find_related_items(
        db, item_id=item_a, user_id=USER_ID,
        category_id=cat["id"], tags=["python", "async"], top_k=5,
    )
    related_ids = [r["id"] for r in related]
    # item_b shares both tags with item_a
    assert item_b in related_ids


@pytest.mark.asyncio
async def test_same_category_found(db):
    cat, cat2, item_a, item_b, item_c, item_d = await _seed_items(db)
    # item_c is in same category as item_a but has no shared tags
    related = await find_related_items(
        db, item_id=item_a, user_id=USER_ID,
        category_id=cat["id"], tags=["python", "async"], top_k=5,
    )
    related_ids = [r["id"] for r in related]
    assert item_c in related_ids


@pytest.mark.asyncio
async def test_self_excluded(db):
    cat, cat2, item_a, item_b, item_c, item_d = await _seed_items(db)
    related = await find_related_items(
        db, item_id=item_a, user_id=USER_ID,
        category_id=cat["id"], tags=["python", "async"], top_k=10,
    )
    related_ids = [r["id"] for r in related]
    assert item_a not in related_ids


@pytest.mark.asyncio
async def test_limit_respected(db):
    cat, cat2, item_a, item_b, item_c, item_d = await _seed_items(db)
    related = await find_related_items(
        db, item_id=item_a, user_id=USER_ID,
        category_id=cat["id"], tags=["python", "async"], top_k=1,
    )
    assert len(related) <= 1


@pytest.mark.asyncio
async def test_fts_fallback(db):
    cat, cat2, item_a, item_b, item_c, item_d = await _seed_items(db)
    # item_d is in a different category with no shared tags,
    # but FTS should still find items when there's room
    related = await find_related_items(
        db, item_id=item_d, user_id=USER_ID,
        category_id=cat2["id"], tags=["figma", "design"], top_k=5,
    )
    # FTS may or may not find anything depending on word overlap,
    # but the function should not crash and should return a list
    assert isinstance(related, list)


@pytest.mark.asyncio
async def test_no_related_returns_empty(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Solo", "📁")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Completely unique content xyz123",
        tags=["unique_only_tag"], ai_summary="Completely unique xyz123",
    )
    related = await find_related_items(
        db, item_id=item_id, user_id=USER_ID,
        category_id=cat["id"], tags=["unique_only_tag"], top_k=3,
    )
    assert related == []
