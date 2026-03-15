"""Gold standard: database query function pattern.

All query functions in savebot/db/queries.py follow these rules:
1. async def, first param db: aiosqlite.Connection, second param user_id: int
2. All SQL is parameterized (? placeholders, never f-strings)
3. await db.commit() after any INSERT/UPDATE/DELETE
4. Return types: dict | None for single, list[dict] for multiple, int for counts, bool for success
5. Use _attach_tags(db, items) on any list[dict] of items for consistency
6. Window functions (LAG, LEAD, ROW_NUMBER, COUNT OVER) for navigation queries
"""

from __future__ import annotations

import aiosqlite


# ── Helper (shared, defined once) ─────────────────────────

async def _attach_tags(db: aiosqlite.Connection, items: list[dict]) -> list[dict]:
    """Attach tags to a list of items (avoids N+1 DRY violation)."""
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


# ── Read query (returns list) ─────────────────────────────

async def get_items_by_category(
    db: aiosqlite.Connection, user_id: int, category_id: int, limit: int = 5, offset: int = 0
) -> list[dict]:
    cursor = await db.execute(
        """SELECT * FROM items WHERE category_id = ? AND user_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (category_id, user_id, limit, offset),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


# ── Read query (returns single or None) ───────────────────

async def get_item(db: aiosqlite.Connection, user_id: int, item_id: int) -> dict | None:
    cursor = await db.execute("SELECT * FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
    row = await cursor.fetchone()
    if not row:
        return None
    item = dict(row)
    items = await _attach_tags(db, [item])
    return items[0]


# ── Write query (returns bool for success) ────────────────

async def update_item_category(db: aiosqlite.Connection, user_id: int, item_id: int, category_id: int) -> bool:
    cursor = await db.execute(
        "UPDATE items SET category_id = ? WHERE id = ? AND user_id = ?", (category_id, item_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


# ── Count query ───────────────────────────────────────────

async def count_items_by_tag(db: aiosqlite.Connection, user_id: int, tag: str) -> int:
    cursor = await db.execute(
        """SELECT COUNT(*) AS c FROM item_tags t
           JOIN items i ON i.id = t.item_id
           WHERE t.tag = ? AND i.user_id = ?""",
        (tag, user_id),
    )
    return (await cursor.fetchone())["c"]


# ── Get-or-create pattern ────────────────────────────────

async def get_or_create_category(db: aiosqlite.Connection, user_id: int, name: str, emoji: str = "\U0001f4c1") -> dict:
    cursor = await db.execute("SELECT * FROM categories WHERE name = ? AND user_id = ?", (name, user_id))
    row = await cursor.fetchone()
    if row:
        return dict(row)
    cursor = await db.execute(
        "INSERT INTO categories (name, user_id, emoji) VALUES (?, ?, ?)", (name, user_id, emoji)
    )
    await db.commit()
    return {"id": cursor.lastrowid, "name": name, "user_id": user_id, "emoji": emoji}


# ── Create-only (rejects duplicates) ─────────────────────

async def create_category_manual(db: aiosqlite.Connection, user_id: int, name: str, emoji: str = "\U0001f4c1") -> dict:
    cursor = await db.execute("SELECT * FROM categories WHERE name = ? AND user_id = ?", (name, user_id))
    if await cursor.fetchone():
        raise ValueError(f"Category '{name}' already exists")
    cursor = await db.execute(
        "INSERT INTO categories (name, user_id, emoji) VALUES (?, ?, ?)", (name, user_id, emoji)
    )
    await db.commit()
    return {"id": cursor.lastrowid, "name": name, "user_id": user_id, "emoji": emoji}
