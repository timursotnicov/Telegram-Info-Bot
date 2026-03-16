"""Tests for savebot.db.state_store."""
import pytest
from savebot.db.state_store import set_state, get_state, delete_state, cleanup_expired

USER_ID = 1


@pytest.mark.asyncio
async def test_set_state_creates_new(db):
    await set_state(db, "edit:1:100", USER_ID, "edit_tags", {"item_id": 100})
    result = await get_state(db, "edit:1:100")
    assert result is not None
    assert result["item_id"] == 100


@pytest.mark.asyncio
async def test_set_state_updates_existing(db):
    await set_state(db, "edit:1:100", USER_ID, "edit_tags", {"item_id": 100, "step": 1})
    await set_state(db, "edit:1:100", USER_ID, "edit_tags", {"item_id": 100, "step": 2})
    result = await get_state(db, "edit:1:100")
    assert result["step"] == 2


@pytest.mark.asyncio
async def test_get_state_existing(db):
    await set_state(db, "key:abc", USER_ID, "some_type", {"foo": "bar"})
    result = await get_state(db, "key:abc")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_state_nonexistent(db):
    result = await get_state(db, "nonexistent:key")
    assert result is None


@pytest.mark.asyncio
async def test_delete_state_existing(db):
    await set_state(db, "del:key", USER_ID, "temp", {"x": 1})
    await delete_state(db, "del:key")
    result = await get_state(db, "del:key")
    assert result is None


@pytest.mark.asyncio
async def test_delete_state_nonexistent(db):
    # Should not raise
    await delete_state(db, "never:existed")


@pytest.mark.asyncio
async def test_cleanup_expired_removes_old(db):
    await set_state(db, "old:key", USER_ID, "temp", {"old": True})
    # Manually backdate the created_at to 2 hours ago
    await db.execute(
        "UPDATE pending_states SET created_at = datetime('now', '-2 hours') WHERE key = ?",
        ("old:key",),
    )
    await db.commit()

    await cleanup_expired(db, max_age_minutes=60)
    result = await get_state(db, "old:key")
    assert result is None


@pytest.mark.asyncio
async def test_cleanup_expired_keeps_fresh(db):
    await set_state(db, "fresh:key", USER_ID, "temp", {"fresh": True})
    # This state was just created, so it should survive a 60-minute cleanup
    await cleanup_expired(db, max_age_minutes=60)
    result = await get_state(db, "fresh:key")
    assert result is not None
    assert result["fresh"] is True
