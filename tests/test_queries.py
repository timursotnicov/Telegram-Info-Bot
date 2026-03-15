"""Tests for savebot.db.queries."""
import pytest
from savebot.db import queries

USER_ID = 1
OTHER_USER = 2


@pytest.mark.asyncio
async def test_create_and_get_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    assert cat["name"] == "Test"
    assert cat["id"] is not None

    # Get existing
    same = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    assert same["id"] == cat["id"]


@pytest.mark.asyncio
async def test_get_all_categories(db):
    await queries.get_or_create_category(db, USER_ID, "Alpha", "\U0001f4c1")
    await queries.get_or_create_category(db, USER_ID, "Beta", "\U0001f4c1")

    cats = await queries.get_all_categories(db, USER_ID)
    assert len(cats) == 2
    names = {c["name"] for c in cats}
    assert "Alpha" in names
    assert "Beta" in names


@pytest.mark.asyncio
async def test_delete_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "ToDelete", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Orphan item", tags=[],
    )
    affected = await queries.delete_category(db, USER_ID, cat["id"])
    assert affected == 1

    # Item still exists but category is NULL
    item = await queries.get_item(db, USER_ID, item_id)
    assert item is not None
    assert item["category_id"] is None

    cats = await queries.get_all_categories(db, USER_ID)
    assert len(cats) == 0


@pytest.mark.asyncio
async def test_save_and_get_item(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID,
        category_id=cat["id"],
        content_type="text",
        content_text="Hello world",
        tags=["test", "hello"],
    )
    assert item_id > 0

    item = await queries.get_item(db, USER_ID, item_id)
    assert item is not None
    assert item["content_text"] == "Hello world"
    assert "test" in item["tags"]
    assert "hello" in item["tags"]


@pytest.mark.asyncio
async def test_get_recent_items(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    for i in range(3):
        await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text=f"Item {i}", tags=[],
        )

    recent = await queries.get_recent_items(db, USER_ID, limit=2)
    assert len(recent) == 2
    # All 3 items have the same CURRENT_TIMESTAMP, so just verify limit works
    texts = {r["content_text"] for r in recent}
    assert len(texts) == 2


@pytest.mark.asyncio
async def test_delete_item(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="To delete", tags=[],
    )
    assert await queries.delete_item(db, USER_ID, item_id)
    assert await queries.get_item(db, USER_ID, item_id) is None


@pytest.mark.asyncio
async def test_find_duplicate(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="link", content_text="Check this", tags=[],
        url="https://example.com",
    )
    # Find by URL
    dup = await queries.find_duplicate(db, USER_ID, "anything", "https://example.com")
    assert dup is not None

    # Find by content
    dup2 = await queries.find_duplicate(db, USER_ID, "Check this")
    assert dup2 is not None

    # No duplicate
    dup3 = await queries.find_duplicate(db, USER_ID, "Something else")
    assert dup3 is None


@pytest.mark.asyncio
async def test_search_items(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Python programming tutorial", tags=["python"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="JavaScript basics", tags=["javascript"],
    )

    results = await queries.search_items(db, USER_ID, "python")
    assert len(results) >= 1
    assert "Python" in results[0]["content_text"] or "python" in results[0]["content_text"].lower()


@pytest.mark.asyncio
async def test_search_items_filtered(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Dev", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Rust language guide", tags=["rust"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Go concurrency patterns", tags=["go"],
    )

    # Search by keyword
    results = await queries.search_items_filtered(db, USER_ID, keywords=["Rust"])
    assert len(results) >= 1
    assert "Rust" in results[0]["content_text"]

    # Search by tag hint
    results = await queries.search_items_filtered(db, USER_ID, tag_hint="go")
    assert len(results) >= 1

    # Search by category hint
    results = await queries.search_items_filtered(db, USER_ID, category_hint="Dev")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_pin_and_unpin(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Important", tags=[],
    )

    assert await queries.pin_item(db, USER_ID, item_id)
    pinned = await queries.get_pinned_items(db, USER_ID)
    assert len(pinned) == 1
    assert pinned[0]["id"] == item_id

    assert await queries.unpin_item(db, USER_ID, item_id)
    pinned = await queries.get_pinned_items(db, USER_ID)
    assert len(pinned) == 0


@pytest.mark.asyncio
async def test_readlist(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="link", content_text="Article", tags=[], url="https://example.com",
    )
    # Manually set as unread (normally done in save handler)
    await db.execute("UPDATE items SET is_read = 0 WHERE id = ?", (item_id,))
    await db.commit()

    unread = await queries.get_unread_items(db, USER_ID)
    assert len(unread) == 1

    assert await queries.mark_item_read(db, USER_ID, item_id)
    unread = await queries.get_unread_items(db, USER_ID)
    assert len(unread) == 0


@pytest.mark.asyncio
async def test_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Private", "\U0001f5dd")
    item_id = await queries.save_item(
        db, USER_ID,
        category_id=cat["id"],
        content_type="text",
        content_text="Secret data",
        tags=["private"],
    )

    # Other user can't see it
    item = await queries.get_item(db, OTHER_USER, item_id)
    assert item is None

    items = await queries.get_recent_items(db, OTHER_USER)
    assert len(items) == 0

    tags = await queries.get_all_tags(db, OTHER_USER)
    assert len(tags) == 0


@pytest.mark.asyncio
async def test_stats(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item 1", tags=["a"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item 2", tags=["b"],
    )

    stats = await queries.get_stats(db, USER_ID)
    assert stats["items"] == 2
    assert stats["categories"] == 1
    assert stats["tags"] == 2


@pytest.mark.asyncio
async def test_preferences_default(db):
    prefs = await queries.get_user_preferences(db, USER_ID)
    assert prefs["auto_save"] == 1
    assert prefs["digest_enabled"] == 1


@pytest.mark.asyncio
async def test_preference_update_whitelist(db):
    await queries.update_user_preference(db, USER_ID, "auto_save", 0)
    prefs = await queries.get_user_preferences(db, USER_ID)
    assert prefs["auto_save"] == 0

    # Whitelist rejection
    with pytest.raises(ValueError):
        await queries.update_user_preference(db, USER_ID, "evil_column", "DROP TABLE")


@pytest.mark.asyncio
async def test_get_all_tags(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item", tags=["alpha", "beta"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item 2", tags=["alpha"],
    )

    tags = await queries.get_all_tags(db, USER_ID)
    tag_names = [t["tag"] for t in tags]
    assert "alpha" in tag_names
    assert "beta" in tag_names
    # alpha should be first (count=2)
    assert tags[0]["tag"] == "alpha"
    assert tags[0]["count"] == 2
