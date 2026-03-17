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


@pytest.mark.asyncio
async def test_get_similar_items_fts(db):
    cat1 = await queries.get_or_create_category(db, USER_ID, "A", "\U0001f4c1")
    cat2 = await queries.get_or_create_category(db, USER_ID, "B", "\U0001f4c1")
    item1 = await queries.save_item(
        db, USER_ID, category_id=cat1["id"],
        content_type="text", content_text="Unique alpha content",
        tags=["unique_x"], ai_summary="Kubernetes deployment strategies overview",
    )
    item2 = await queries.save_item(
        db, USER_ID, category_id=cat2["id"],
        content_type="text", content_text="Kubernetes deployment guide with strategies",
        tags=["unique_y"], ai_summary="Kubernetes deployment strategies deep dive",
    )

    similar = await queries.get_similar_items_fts(db, USER_ID, item1, limit=5)
    assert len(similar) >= 1
    assert item2 in [r["id"] for r in similar]
    assert item1 not in [r["id"] for r in similar]
    # Tags should be attached
    for r in similar:
        assert "tags" in r


@pytest.mark.asyncio
async def test_get_similar_items_fts_no_summary(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Solo", "\U0001f4c1")
    item1 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="No summary item", tags=[],
    )
    similar = await queries.get_similar_items_fts(db, USER_ID, item1, limit=5)
    assert similar == []


@pytest.mark.asyncio
async def test_get_similar_items_fts_user_isolation(db):
    cat1 = await queries.get_or_create_category(db, USER_ID, "Cat", "\U0001f4c1")
    cat2 = await queries.get_or_create_category(db, OTHER_USER, "Cat", "\U0001f4c1")
    item1 = await queries.save_item(
        db, USER_ID, category_id=cat1["id"],
        content_type="text", content_text="My Kubernetes guide",
        tags=[], ai_summary="Kubernetes deployment strategies",
    )
    await queries.save_item(
        db, OTHER_USER, category_id=cat2["id"],
        content_type="text", content_text="Kubernetes deployment other user",
        tags=[], ai_summary="Kubernetes deployment strategies other",
    )

    similar = await queries.get_similar_items_fts(db, USER_ID, item1, limit=5)
    for r in similar:
        assert r["user_id"] == USER_ID


# ── Collections ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_collections(db):
    coll = await queries.create_collection(db, USER_ID, "Favorites", "⭐")
    assert coll["name"] == "Favorites"
    assert coll["id"] is not None

    colls = await queries.get_collections(db, USER_ID)
    assert len(colls) == 1
    assert colls[0]["name"] == "Favorites"
    assert colls[0]["item_count"] == 0


@pytest.mark.asyncio
async def test_add_and_get_collection_items(db):
    coll = await queries.create_collection(db, USER_ID, "Reading", "📖")
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Article", tags=["read"],
    )

    assert await queries.add_to_collection(db, USER_ID, coll["id"], item_id)

    items = await queries.get_collection_items(db, USER_ID, coll["id"])
    assert len(items) == 1
    assert items[0]["id"] == item_id
    assert "tags" in items[0]

    # item_count should update
    colls = await queries.get_collections(db, USER_ID)
    assert colls[0]["item_count"] == 1


@pytest.mark.asyncio
async def test_add_to_collection_duplicate(db):
    coll = await queries.create_collection(db, USER_ID, "Dupes", "📁")
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item", tags=[],
    )

    assert await queries.add_to_collection(db, USER_ID, coll["id"], item_id)
    # Second add should return False (duplicate)
    assert not await queries.add_to_collection(db, USER_ID, coll["id"], item_id)


@pytest.mark.asyncio
async def test_remove_from_collection(db):
    coll = await queries.create_collection(db, USER_ID, "Temp", "📁")
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Removable", tags=[],
    )

    await queries.add_to_collection(db, USER_ID, coll["id"], item_id)
    assert await queries.remove_from_collection(db, USER_ID, coll["id"], item_id)

    items = await queries.get_collection_items(db, USER_ID, coll["id"])
    assert len(items) == 0


@pytest.mark.asyncio
async def test_delete_collection(db):
    coll = await queries.create_collection(db, USER_ID, "ToDelete", "📁")
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Kept item", tags=[],
    )
    await queries.add_to_collection(db, USER_ID, coll["id"], item_id)

    assert await queries.delete_collection(db, USER_ID, coll["id"])

    colls = await queries.get_collections(db, USER_ID)
    assert len(colls) == 0

    # Item itself still exists
    item = await queries.get_item(db, USER_ID, item_id)
    assert item is not None


@pytest.mark.asyncio
async def test_collection_user_isolation(db):
    coll = await queries.create_collection(db, USER_ID, "Private", "🔒")
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Secret", tags=[],
    )
    await queries.add_to_collection(db, USER_ID, coll["id"], item_id)

    # Other user can't see collections
    colls = await queries.get_collections(db, OTHER_USER)
    assert len(colls) == 0

    # Other user can't add to this collection
    cat2 = await queries.get_or_create_category(db, OTHER_USER, "Test", "\U0001f4c1")
    item2 = await queries.save_item(
        db, OTHER_USER, category_id=cat2["id"],
        content_type="text", content_text="Other", tags=[],
    )
    assert not await queries.add_to_collection(db, OTHER_USER, coll["id"], item2)

    # Other user can't delete this collection
    assert not await queries.delete_collection(db, OTHER_USER, coll["id"])


# ── Daily Brief ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_items_saved_yesterday(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Recent item", tags=["daily"],
    )
    # Insert an old item manually
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, created_at)
           VALUES (?, 'text', 'Old item', ?, datetime('now', '-3 days'))""",
        (cat["id"], USER_ID),
    )
    await db.commit()

    items = await queries.get_items_saved_yesterday(db, USER_ID)
    texts = [i["content_text"] for i in items]
    assert "Recent item" in texts
    assert "Old item" not in texts
    # Tags attached
    for item in items:
        assert "tags" in item


@pytest.mark.asyncio
async def test_get_items_on_this_day(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Test", "\U0001f4c1")
    # Insert item on same month+day but last year
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, created_at)
           VALUES (?, 'text', 'Anniversary item', ?, datetime('now', '-1 year'))""",
        (cat["id"], USER_ID),
    )
    # Insert item on a different day last year
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, created_at)
           VALUES (?, 'text', 'Different day item', ?, datetime('now', '-1 year', '+5 days'))""",
        (cat["id"], USER_ID),
    )
    await db.commit()

    items = await queries.get_items_on_this_day(db, USER_ID)
    texts = [i["content_text"] for i in items]
    assert "Anniversary item" in texts
    assert "Different day item" not in texts


@pytest.mark.asyncio
async def test_get_weekly_category_stats(db):
    cat1 = await queries.get_or_create_category(db, USER_ID, "Work", "💼")
    cat2 = await queries.get_or_create_category(db, USER_ID, "Fun", "🎮")
    for _ in range(3):
        await queries.save_item(
            db, USER_ID, category_id=cat1["id"],
            content_type="text", content_text="Work item", tags=[],
        )
    await queries.save_item(
        db, USER_ID, category_id=cat2["id"],
        content_type="text", content_text="Fun item", tags=[],
    )

    stats = await queries.get_weekly_category_stats(db, USER_ID)
    assert len(stats) == 2
    assert stats[0]["name"] == "Work"
    assert stats[0]["count"] == 3
    assert stats[1]["name"] == "Fun"
    assert stats[1]["count"] == 1


@pytest.mark.asyncio
async def test_get_inbox_count(db):
    inbox = await queries.get_or_create_inbox_category(db, USER_ID)
    other = await queries.get_or_create_category(db, USER_ID, "Other", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=inbox["id"],
        content_type="text", content_text="Inbox item 1", tags=[],
    )
    await queries.save_item(
        db, USER_ID, category_id=inbox["id"],
        content_type="text", content_text="Inbox item 2", tags=[],
    )
    await queries.save_item(
        db, USER_ID, category_id=other["id"],
        content_type="text", content_text="Not inbox", tags=[],
    )

    count = await queries.get_inbox_count(db, USER_ID)
    assert count == 2


@pytest.mark.asyncio
async def test_daily_brief_preferences(db):
    prefs = await queries.get_user_preferences(db, USER_ID)
    assert prefs["daily_brief_enabled"] == 0
    assert prefs["daily_brief_time"] == "09:00"

    await queries.update_user_preference(db, USER_ID, "daily_brief_enabled", 1)
    await queries.update_user_preference(db, USER_ID, "daily_brief_time", "08:00")
    prefs = await queries.get_user_preferences(db, USER_ID)
    assert prefs["daily_brief_enabled"] == 1
    assert prefs["daily_brief_time"] == "08:00"


@pytest.mark.asyncio
async def test_get_all_users_with_daily_brief(db):
    # No users initially
    users = await queries.get_all_users_with_daily_brief(db)
    assert len(users) == 0

    # Enable for USER_ID
    await queries.update_user_preference(db, USER_ID, "daily_brief_enabled", 1)
    users = await queries.get_all_users_with_daily_brief(db)
    assert len(users) == 1
    assert users[0]["user_id"] == USER_ID


# ── rename_category ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "OldName", "\U0001f4c1")
    result = await queries.rename_category(db, USER_ID, cat["id"], "NewName")
    assert result is True

    cats = await queries.get_all_categories(db, USER_ID)
    assert cats[0]["name"] == "NewName"


@pytest.mark.asyncio
async def test_rename_category_nonexistent(db):
    result = await queries.rename_category(db, USER_ID, 9999, "Ghost")
    assert result is False


@pytest.mark.asyncio
async def test_rename_category_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Mine", "\U0001f4c1")
    result = await queries.rename_category(db, OTHER_USER, cat["id"], "Stolen")
    assert result is False
    # Original name unchanged
    cats = await queries.get_all_categories(db, USER_ID)
    assert cats[0]["name"] == "Mine"


# ── merge_categories ────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_categories(db):
    src = await queries.get_or_create_category(db, USER_ID, "Source", "\U0001f4c1")
    tgt = await queries.get_or_create_category(db, USER_ID, "Target", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=src["id"],
        content_type="text", content_text="Movable", tags=[],
    )

    affected = await queries.merge_categories(db, USER_ID, src["id"], tgt["id"])
    assert affected == 1

    # Item is now in target
    item = await queries.get_item(db, USER_ID, item_id)
    assert item["category_id"] == tgt["id"]

    # Source category deleted
    cats = await queries.get_all_categories(db, USER_ID)
    names = {c["name"] for c in cats}
    assert "Source" not in names
    assert "Target" in names


@pytest.mark.asyncio
async def test_merge_categories_empty_source(db):
    src = await queries.get_or_create_category(db, USER_ID, "Empty", "\U0001f4c1")
    tgt = await queries.get_or_create_category(db, USER_ID, "Target", "\U0001f4c1")
    affected = await queries.merge_categories(db, USER_ID, src["id"], tgt["id"])
    assert affected == 0


# ── get_items_by_category ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_items_by_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Cat1", "\U0001f4c1")
    for i in range(3):
        await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text=f"CatItem {i}", tags=["x"],
        )

    items = await queries.get_items_by_category(db, USER_ID, cat["id"], limit=5)
    assert len(items) == 3
    assert all("tags" in it for it in items)


@pytest.mark.asyncio
async def test_get_items_by_category_pagination(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Paged", "\U0001f4c1")
    for i in range(5):
        await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text=f"P{i}", tags=[],
        )

    page1 = await queries.get_items_by_category(db, USER_ID, cat["id"], limit=2, offset=0)
    page2 = await queries.get_items_by_category(db, USER_ID, cat["id"], limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    ids1 = {it["id"] for it in page1}
    ids2 = {it["id"] for it in page2}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_get_items_by_category_empty(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Empty", "\U0001f4c1")
    items = await queries.get_items_by_category(db, USER_ID, cat["id"])
    assert items == []


@pytest.mark.asyncio
async def test_get_items_by_category_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Private", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Secret", tags=[],
    )
    items = await queries.get_items_by_category(db, OTHER_USER, cat["id"])
    assert items == []


# ── get_items_by_tag ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_items_by_tag(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Tagged1", tags=["alpha", "beta"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Tagged2", tags=["alpha"],
    )

    items = await queries.get_items_by_tag(db, USER_ID, "alpha")
    assert len(items) == 2
    items_beta = await queries.get_items_by_tag(db, USER_ID, "beta")
    assert len(items_beta) == 1


@pytest.mark.asyncio
async def test_get_items_by_tag_empty(db):
    items = await queries.get_items_by_tag(db, USER_ID, "nonexistent")
    assert items == []


@pytest.mark.asyncio
async def test_get_items_by_tag_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Mine", tags=["secret_tag"],
    )
    items = await queries.get_items_by_tag(db, OTHER_USER, "secret_tag")
    assert items == []


# ── update_item_category ────────────────────────────────────


@pytest.mark.asyncio
async def test_update_item_category(db):
    cat1 = await queries.get_or_create_category(db, USER_ID, "A", "\U0001f4c1")
    cat2 = await queries.get_or_create_category(db, USER_ID, "B", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat1["id"],
        content_type="text", content_text="Move me", tags=[],
    )

    result = await queries.update_item_category(db, USER_ID, item_id, cat2["id"])
    assert result is True

    item = await queries.get_item(db, USER_ID, item_id)
    assert item["category_id"] == cat2["id"]


@pytest.mark.asyncio
async def test_update_item_category_nonexistent(db):
    cat = await queries.get_or_create_category(db, USER_ID, "A", "\U0001f4c1")
    result = await queries.update_item_category(db, USER_ID, 9999, cat["id"])
    assert result is False


@pytest.mark.asyncio
async def test_update_item_category_user_isolation(db):
    cat1 = await queries.get_or_create_category(db, USER_ID, "A", "\U0001f4c1")
    cat2 = await queries.get_or_create_category(db, OTHER_USER, "B", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat1["id"],
        content_type="text", content_text="Protected", tags=[],
    )
    result = await queries.update_item_category(db, OTHER_USER, item_id, cat2["id"])
    assert result is False


# ── update_item_tags ────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_item_tags(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Taggable", tags=["old"],
    )

    await queries.update_item_tags(db, USER_ID, item_id, ["new1", "new2"])
    item = await queries.get_item(db, USER_ID, item_id)
    assert set(item["tags"]) == {"new1", "new2"}


@pytest.mark.asyncio
async def test_update_item_tags_empty(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="ClearTags", tags=["remove_me"],
    )

    await queries.update_item_tags(db, USER_ID, item_id, [])
    item = await queries.get_item(db, USER_ID, item_id)
    assert item["tags"] == []


@pytest.mark.asyncio
async def test_update_item_tags_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Protected", tags=["original"],
    )

    # Other user tries to change tags — should do nothing
    await queries.update_item_tags(db, OTHER_USER, item_id, ["hacked"])
    item = await queries.get_item(db, USER_ID, item_id)
    assert item["tags"] == ["original"]


# ── update_item_note ────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_item_note_add(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Noted", tags=[],
    )

    result = await queries.update_item_note(db, USER_ID, item_id, "My note")
    assert result is True

    item = await queries.get_item(db, USER_ID, item_id)
    assert item["user_note"] == "My note"


@pytest.mark.asyncio
async def test_update_item_note_overwrite(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Noted", tags=[],
    )

    await queries.update_item_note(db, USER_ID, item_id, "First")
    await queries.update_item_note(db, USER_ID, item_id, "Second")
    item = await queries.get_item(db, USER_ID, item_id)
    assert item["user_note"] == "Second"


@pytest.mark.asyncio
async def test_update_item_note_nonexistent(db):
    result = await queries.update_item_note(db, USER_ID, 9999, "Ghost note")
    assert result is False


# ── export_all ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_all(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Export", "\U0001f4e6")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Export1", tags=["e1"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Export2", tags=["e2"],
    )

    data = await queries.export_all(db, USER_ID)
    assert len(data) == 2
    assert all("category_name" in d for d in data)
    assert all("category_emoji" in d for d in data)
    assert all("tags" in d for d in data)


@pytest.mark.asyncio
async def test_export_all_empty(db):
    data = await queries.export_all(db, USER_ID)
    assert data == []


@pytest.mark.asyncio
async def test_export_all_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Mine", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Private", tags=[],
    )

    data = await queries.export_all(db, OTHER_USER)
    assert data == []


# ── count_items_in_category ─────────────────────────────────


@pytest.mark.asyncio
async def test_count_items_in_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Counted", "\U0001f4c1")
    for _ in range(3):
        await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text="X", tags=[],
        )

    count = await queries.count_items_in_category(db, USER_ID, cat["id"])
    assert count == 3


@pytest.mark.asyncio
async def test_count_items_in_category_empty(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Empty", "\U0001f4c1")
    count = await queries.count_items_in_category(db, USER_ID, cat["id"])
    assert count == 0


@pytest.mark.asyncio
async def test_count_items_in_category_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Mine", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="X", tags=[],
    )
    count = await queries.count_items_in_category(db, OTHER_USER, cat["id"])
    assert count == 0


# ── count_items_by_tag ──────────────────────────────────────


@pytest.mark.asyncio
async def test_count_items_by_tag(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="A", tags=["counted"],
    )
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="B", tags=["counted"],
    )

    count = await queries.count_items_by_tag(db, USER_ID, "counted")
    assert count == 2


@pytest.mark.asyncio
async def test_count_items_by_tag_nonexistent(db):
    count = await queries.count_items_by_tag(db, USER_ID, "no_such_tag")
    assert count == 0


@pytest.mark.asyncio
async def test_count_items_by_tag_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="X", tags=["private_tag"],
    )
    count = await queries.count_items_by_tag(db, OTHER_USER, "private_tag")
    assert count == 0


# ── get_category_tag_map ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_category_tag_map(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Mapped", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="X", tags=["t1", "t2"],
    )

    result = await queries.get_category_tag_map(db, USER_ID)
    assert len(result) == 1
    assert result[0]["name"] == "Mapped"
    assert "t1" in result[0]["top_tags"]
    assert "t2" in result[0]["top_tags"]


@pytest.mark.asyncio
async def test_get_category_tag_map_empty(db):
    result = await queries.get_category_tag_map(db, USER_ID)
    assert result == []


# ── get_items_with_shared_tags ──────────────────────────────


@pytest.mark.asyncio
async def test_get_items_with_shared_tags(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    id1 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item1", tags=["a", "b", "c"],
    )
    id2 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item2", tags=["a", "b"],
    )
    # This item shares only 1 tag — below min_shared=2
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Item3", tags=["a"],
    )

    related = await queries.get_items_with_shared_tags(db, USER_ID, id1, min_shared=2)
    ids = [r["id"] for r in related]
    assert id2 in ids
    assert id1 not in ids  # exclude self


@pytest.mark.asyncio
async def test_get_items_with_shared_tags_none(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    id1 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Lonely", tags=["unique_z"],
    )

    related = await queries.get_items_with_shared_tags(db, USER_ID, id1)
    assert related == []


# ── get_items_in_same_category ──────────────────────────────


@pytest.mark.asyncio
async def test_get_items_in_same_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "SameCat", "\U0001f4c1")
    id1 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Self", tags=[],
    )
    id2 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Sibling", tags=[],
    )

    siblings = await queries.get_items_in_same_category(db, USER_ID, id1, cat["id"])
    ids = [r["id"] for r in siblings]
    assert id2 in ids
    assert id1 not in ids  # self excluded


@pytest.mark.asyncio
async def test_get_items_in_same_category_empty(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Alone", "\U0001f4c1")
    id1 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Only", tags=[],
    )

    siblings = await queries.get_items_in_same_category(db, USER_ID, id1, cat["id"])
    assert siblings == []


# ── get_adjacent_item_ids ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_adjacent_item_ids_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Nav", "\U0001f4c1")
    ids = []
    for i in range(3):
        iid = await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text=f"Nav{i}", tags=[],
        )
        ids.append(iid)

    # Items ordered by created_at DESC, so ids[2] is first, ids[0] is last
    nav = await queries.get_adjacent_item_ids(db, USER_ID, ids[1], "category", cat["id"])
    assert nav is not None
    assert nav["total"] == 3
    assert nav["prev_id"] is not None or nav["next_id"] is not None


@pytest.mark.asyncio
async def test_get_adjacent_item_ids_recent(db):
    cat = await queries.get_or_create_category(db, USER_ID, "R", "\U0001f4c1")
    id1 = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="R1", tags=[],
    )

    nav = await queries.get_adjacent_item_ids(db, USER_ID, id1, "recent")
    assert nav is not None
    assert nav["total"] == 1
    assert nav["prev_id"] is None
    assert nav["next_id"] is None


@pytest.mark.asyncio
async def test_get_adjacent_item_ids_nonexistent(db):
    nav = await queries.get_adjacent_item_ids(db, USER_ID, 9999, "recent")
    assert nav is None


# ── get_items_page_with_nums ────────────────────────────────


@pytest.mark.asyncio
async def test_get_items_page_with_nums_recent(db):
    cat = await queries.get_or_create_category(db, USER_ID, "P", "\U0001f4c1")
    for i in range(5):
        await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text=f"Page{i}", tags=[],
        )

    page = await queries.get_items_page_with_nums(db, USER_ID, "recent", limit=3, offset=0)
    assert len(page) == 3
    assert all("display_num" in it for it in page)
    assert all("category_name" in it for it in page)
    assert all("tags" in it for it in page)
    # First page display_nums should be 1,2,3
    nums = [it["display_num"] for it in page]
    assert nums == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_items_page_with_nums_pinned(db):
    cat = await queries.get_or_create_category(db, USER_ID, "P", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Pinned", tags=[],
    )
    await queries.pin_item(db, USER_ID, item_id)

    page = await queries.get_items_page_with_nums(db, USER_ID, "pinned", limit=5)
    assert len(page) == 1
    assert page[0]["display_num"] == 1


@pytest.mark.asyncio
async def test_get_items_page_with_nums_forgotten(db):
    cat = await queries.get_or_create_category(db, USER_ID, "P", "\U0001f4c1")
    # Insert an old unpinned item
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, is_pinned, created_at)
           VALUES (?, 'text', 'Old item', ?, 0, datetime('now', '-60 days'))""",
        (cat["id"], USER_ID),
    )
    await db.commit()

    page = await queries.get_items_page_with_nums(db, USER_ID, "forgotten", limit=5)
    assert len(page) == 1
    assert page[0]["content_text"] == "Old item"


@pytest.mark.asyncio
async def test_get_items_page_with_nums_category(db):
    cat = await queries.get_or_create_category(db, USER_ID, "Specific", "\U0001f4c1")
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="In cat", tags=[],
    )

    page = await queries.get_items_page_with_nums(
        db, USER_ID, "category", context_id=cat["id"], limit=5,
    )
    assert len(page) == 1
    assert page[0]["category_name"] == "Specific"


@pytest.mark.asyncio
async def test_get_items_page_with_nums_empty(db):
    page = await queries.get_items_page_with_nums(db, USER_ID, "recent", limit=5)
    assert page == []


# ── create_category_manual ──────────────────────────────────


@pytest.mark.asyncio
async def test_create_category_manual(db):
    cat = await queries.create_category_manual(db, USER_ID, "Fresh", "\U0001f195")
    assert cat["name"] == "Fresh"
    assert cat["id"] is not None


@pytest.mark.asyncio
async def test_create_category_manual_duplicate(db):
    await queries.create_category_manual(db, USER_ID, "Unique", "\U0001f4c1")
    with pytest.raises(ValueError, match="already exists"):
        await queries.create_category_manual(db, USER_ID, "Unique", "\U0001f4c1")


# ── count_collection_items ──────────────────────────────────


@pytest.mark.asyncio
async def test_count_collection_items(db):
    coll = await queries.create_collection(db, USER_ID, "Counted", "\U0001f4c1")
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    for i in range(2):
        item_id = await queries.save_item(
            db, USER_ID, category_id=cat["id"],
            content_type="text", content_text=f"C{i}", tags=[],
        )
        await queries.add_to_collection(db, USER_ID, coll["id"], item_id)

    count = await queries.count_collection_items(db, USER_ID, coll["id"])
    assert count == 2


@pytest.mark.asyncio
async def test_count_collection_items_empty(db):
    coll = await queries.create_collection(db, USER_ID, "Empty", "\U0001f4c1")
    count = await queries.count_collection_items(db, USER_ID, coll["id"])
    assert count == 0


@pytest.mark.asyncio
async def test_count_collection_items_user_isolation(db):
    coll = await queries.create_collection(db, USER_ID, "Mine", "\U0001f4c1")
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    item_id = await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="X", tags=[],
    )
    await queries.add_to_collection(db, USER_ID, coll["id"], item_id)

    # Other user can't count
    count = await queries.count_collection_items(db, OTHER_USER, coll["id"])
    assert count == 0


# ── get_forgotten_items ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_forgotten_items(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    # Old unpinned item
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, is_pinned, created_at)
           VALUES (?, 'text', 'Forgotten', ?, 0, datetime('now', '-60 days'))""",
        (cat["id"], USER_ID),
    )
    # Recent item — should NOT appear
    await queries.save_item(
        db, USER_ID, category_id=cat["id"],
        content_type="text", content_text="Recent", tags=[],
    )
    # Old pinned item — should NOT appear
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, is_pinned, created_at)
           VALUES (?, 'text', 'Pinned old', ?, 1, datetime('now', '-60 days'))""",
        (cat["id"], USER_ID),
    )
    await db.commit()

    items = await queries.get_forgotten_items(db, USER_ID, days=30)
    texts = [i["content_text"] for i in items]
    assert "Forgotten" in texts
    assert "Recent" not in texts
    assert "Pinned old" not in texts


@pytest.mark.asyncio
async def test_get_forgotten_items_empty(db):
    items = await queries.get_forgotten_items(db, USER_ID)
    assert items == []


@pytest.mark.asyncio
async def test_get_forgotten_items_user_isolation(db):
    cat = await queries.get_or_create_category(db, USER_ID, "T", "\U0001f4c1")
    await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, user_id, is_pinned, created_at)
           VALUES (?, 'text', 'Old', ?, 0, datetime('now', '-60 days'))""",
        (cat["id"], USER_ID),
    )
    await db.commit()

    items = await queries.get_forgotten_items(db, OTHER_USER, days=30)
    assert items == []


# ── _escape_fts5 ────────────────────────────────────────────


def test_escape_fts5_basic():
    result = queries._escape_fts5(["hello", "world"])
    assert result == '"hello" "world"'


def test_escape_fts5_strips_quotes():
    result = queries._escape_fts5(['"evil"', 'nor"mal'])
    assert result == '"evil" "normal"'


def test_escape_fts5_empty_terms():
    result = queries._escape_fts5(["", "  ", "ok"])
    assert result == '"ok"'


def test_escape_fts5_all_empty():
    result = queries._escape_fts5(["", "  "])
    assert result == ""


def test_escape_fts5_special_chars():
    # FTS5 special chars like * and - should be wrapped safely in quotes
    result = queries._escape_fts5(["C++", "node.js"])
    assert result == '"C++" "node.js"'
