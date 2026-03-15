"""Database query functions."""

from __future__ import annotations

import json
from typing import Any

import aiosqlite


# ── Allowed preference keys (whitelist for SQL injection prevention) ──

_ALLOWED_PREF_KEYS = {"auto_save", "digest_enabled", "digest_day", "digest_time", "language"}


# ── Helper ─────────────────────────────────────────────────

async def _attach_tags(db: aiosqlite.Connection, items: list[dict]) -> list[dict]:
    """Attach tags to a list of items (avoids N+1 DRY violation)."""
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


# ── Categories ──────────────────────────────────────────────

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


async def get_all_categories(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    cursor = await db.execute(
        """SELECT c.*, COUNT(i.id) as item_count
           FROM categories c
           LEFT JOIN items i ON i.category_id = c.id
           WHERE c.user_id = ?
           GROUP BY c.id
           ORDER BY item_count DESC""",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def rename_category(db: aiosqlite.Connection, user_id: int, cat_id: int, new_name: str) -> bool:
    cursor = await db.execute(
        "UPDATE categories SET name = ? WHERE id = ? AND user_id = ?", (new_name, cat_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_category(db: aiosqlite.Connection, user_id: int, cat_id: int) -> int:
    cursor = await db.execute(
        "UPDATE items SET category_id = NULL WHERE category_id = ? AND user_id = ?", (cat_id, user_id)
    )
    affected = cursor.rowcount
    await db.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (cat_id, user_id))
    await db.commit()
    return affected


async def merge_categories(db: aiosqlite.Connection, user_id: int, source_id: int, target_id: int) -> int:
    cursor = await db.execute(
        "UPDATE items SET category_id = ? WHERE category_id = ? AND user_id = ?", (target_id, source_id, user_id)
    )
    affected = cursor.rowcount
    await db.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (source_id, user_id))
    await db.commit()
    return affected


# ── Items ───────────────────────────────────────────────────

async def save_item(
    db: aiosqlite.Connection,
    user_id: int,
    category_id: int,
    content_type: str,
    content_text: str,
    tags: list[str],
    url: str | None = None,
    file_id: str | None = None,
    source: str | None = None,
    ai_summary: str | None = None,
    tg_message_id: int | None = None,
) -> int:
    cursor = await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, url, file_id, source, ai_summary, tg_message_id, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (category_id, content_type, content_text, url, file_id, source, ai_summary, tg_message_id, user_id),
    )
    item_id = cursor.lastrowid
    for tag in tags:
        await db.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )
    await db.commit()
    return item_id


async def get_item(db: aiosqlite.Connection, user_id: int, item_id: int) -> dict | None:
    cursor = await db.execute("SELECT * FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
    row = await cursor.fetchone()
    if not row:
        return None
    item = dict(row)
    items = await _attach_tags(db, [item])
    return items[0]


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


async def get_items_by_tag(
    db: aiosqlite.Connection, user_id: int, tag: str, limit: int = 5, offset: int = 0
) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.* FROM items i
           JOIN item_tags t ON t.item_id = i.id
           WHERE t.tag = ? AND i.user_id = ?
           ORDER BY i.created_at DESC LIMIT ? OFFSET ?""",
        (tag, user_id, limit, offset),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def search_items(db: aiosqlite.Connection, user_id: int, query: str, limit: int = 10) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.*, highlight(items_fts, 0, '<b>', '</b>') as highlighted
           FROM items_fts fts
           JOIN items i ON i.id = fts.rowid
           WHERE items_fts MATCH ? AND i.user_id = ?
           ORDER BY rank
           LIMIT ?""",
        (query, user_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def get_recent_items(db: aiosqlite.Connection, user_id: int, limit: int = 10) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM items WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def update_item_category(db: aiosqlite.Connection, user_id: int, item_id: int, category_id: int) -> bool:
    cursor = await db.execute(
        "UPDATE items SET category_id = ? WHERE id = ? AND user_id = ?", (category_id, item_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_item_tags(db: aiosqlite.Connection, user_id: int, item_id: int, tags: list[str]) -> None:
    # Verify item belongs to user
    cursor = await db.execute("SELECT id FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
    if not await cursor.fetchone():
        return
    await db.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
    for tag in tags:
        await db.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )
    await db.commit()


async def delete_item(db: aiosqlite.Connection, user_id: int, item_id: int) -> bool:
    cursor = await db.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
    await db.commit()
    return cursor.rowcount > 0


async def find_duplicate(db: aiosqlite.Connection, user_id: int, content_text: str, url: str | None = None) -> dict | None:
    if url:
        cursor = await db.execute("SELECT * FROM items WHERE url = ? AND user_id = ?", (url, user_id))
        row = await cursor.fetchone()
        if row:
            return dict(row)
    cursor = await db.execute("SELECT * FROM items WHERE content_text = ? AND user_id = ?", (content_text, user_id))
    row = await cursor.fetchone()
    return dict(row) if row else None


# ── Tags ────────────────────────────────────────────────────

async def get_all_tags(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    cursor = await db.execute(
        """SELECT t.tag, COUNT(*) as count
           FROM item_tags t
           JOIN items i ON i.id = t.item_id
           WHERE i.user_id = ?
           GROUP BY t.tag
           ORDER BY count DESC""",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


# ── Stats ───────────────────────────────────────────────────

async def get_stats(db: aiosqlite.Connection, user_id: int) -> dict:
    items = await db.execute("SELECT COUNT(*) as c FROM items WHERE user_id = ?", (user_id,))
    items_count = (await items.fetchone())["c"]
    cats = await db.execute("SELECT COUNT(*) as c FROM categories WHERE user_id = ?", (user_id,))
    cats_count = (await cats.fetchone())["c"]
    tags = await db.execute(
        "SELECT COUNT(DISTINCT t.tag) as c FROM item_tags t JOIN items i ON i.id = t.item_id WHERE i.user_id = ?",
        (user_id,),
    )
    tags_count = (await tags.fetchone())["c"]
    return {"items": items_count, "categories": cats_count, "tags": tags_count}


# ── Export ──────────────────────────────────────────────────

async def export_all(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.*, c.name as category_name, c.emoji as category_emoji
           FROM items i
           LEFT JOIN categories c ON c.id = i.category_id
           WHERE i.user_id = ?
           ORDER BY i.created_at DESC""",
        (user_id,),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def count_items_in_category(db: aiosqlite.Connection, user_id: int, category_id: int) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) as c FROM items WHERE category_id = ? AND user_id = ?", (category_id, user_id)
    )
    return (await cursor.fetchone())["c"]


# ── User Preferences ───────────────────────────────────────

async def get_user_preferences(db: aiosqlite.Connection, user_id: int) -> dict:
    cursor = await db.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    if row:
        return dict(row)
    # Create default preferences
    await db.execute(
        "INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,)
    )
    await db.commit()
    return {"user_id": user_id, "auto_save": 1, "digest_enabled": 1, "digest_day": 1, "digest_time": "10:00", "language": "ru"}


async def update_user_preference(db: aiosqlite.Connection, user_id: int, key: str, value: Any):
    if key not in _ALLOWED_PREF_KEYS:
        raise ValueError(f"Invalid preference key: {key}")
    await db.execute("INSERT OR IGNORE INTO user_preferences (user_id) VALUES (?)", (user_id,))
    await db.execute(f"UPDATE user_preferences SET {key} = ? WHERE user_id = ?", (value, user_id))
    await db.commit()


# ── Weekly / Digest ─────────────────────────────────────────

async def get_items_this_week(db: aiosqlite.Connection, user_id: int, limit: int = 50) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.*, c.name as category_name, c.emoji as category_emoji
           FROM items i LEFT JOIN categories c ON c.id = i.category_id
           WHERE i.user_id = ? AND i.created_at >= datetime('now', '-7 days')
           ORDER BY i.created_at DESC LIMIT ?""",
        (user_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def get_items_on_this_week(db: aiosqlite.Connection, user_id: int, limit: int = 5) -> list[dict]:
    """Items saved in the same week-of-year in previous months/years."""
    cursor = await db.execute(
        """SELECT i.*, c.name as category_name, c.emoji as category_emoji,
                  i.created_at as saved_at
           FROM items i LEFT JOIN categories c ON c.id = i.category_id
           WHERE i.user_id = ?
             AND i.created_at < datetime('now', '-30 days')
             AND CAST(strftime('%W', i.created_at) AS INTEGER) = CAST(strftime('%W', 'now') AS INTEGER)
           ORDER BY i.created_at DESC LIMIT ?""",
        (user_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def get_weekly_stats(db: aiosqlite.Connection, user_id: int) -> dict:
    total = await db.execute("SELECT COUNT(*) as c FROM items WHERE user_id = ?", (user_id,))
    total_count = (await total.fetchone())[0]
    week = await db.execute(
        "SELECT COUNT(*) as c FROM items WHERE user_id = ? AND created_at >= datetime('now', '-7 days')",
        (user_id,),
    )
    week_count = (await week.fetchone())[0]
    cats = await db.execute("SELECT COUNT(*) as c FROM categories WHERE user_id = ?", (user_id,))
    cats_count = (await cats.fetchone())[0]
    tags = await db.execute(
        "SELECT COUNT(DISTINCT t.tag) as c FROM item_tags t JOIN items i ON i.id = t.item_id WHERE i.user_id = ?",
        (user_id,),
    )
    tags_count = (await tags.fetchone())[0]
    return {"total_items": total_count, "week_items": week_count, "categories": cats_count, "tags": tags_count}


async def get_all_users_with_digest(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM user_preferences WHERE digest_enabled = 1"
    )
    return [dict(r) for r in await cursor.fetchall()]


async def log_digest(db: aiosqlite.Connection, user_id: int, item_ids: list[int]):
    await db.execute(
        "INSERT INTO digest_log (user_id, items_included) VALUES (?, ?)",
        (user_id, json.dumps(item_ids)),
    )
    await db.commit()


def _escape_fts5(terms: list[str]) -> str:
    """Escape terms for FTS5 MATCH. Wraps each term in double quotes."""
    cleaned = []
    for term in terms:
        t = term.replace('"', '').strip()
        if t:
            cleaned.append(f'"{t}"')
    return " ".join(cleaned)


async def search_items_filtered(
    db: aiosqlite.Connection,
    user_id: int,
    keywords: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    category_hint: str | None = None,
    tag_hint: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """Search items with AI-parsed filters: keywords (FTS5) + date + category + tag."""
    conditions = ["i.user_id = ?"]
    params: list = [user_id]
    use_fts = False

    if keywords:
        fts_query = _escape_fts5(keywords)
        if fts_query:
            use_fts = True
            conditions.append("items_fts MATCH ?")
            params.append(fts_query)

    if date_from:
        conditions.append("i.created_at >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("i.created_at <= ?")
        params.append(date_to + " 23:59:59")

    if category_hint:
        conditions.append("i.category_id IN (SELECT id FROM categories WHERE name LIKE ? AND user_id = ?)")
        params.extend([f"%{category_hint}%", user_id])

    if tag_hint:
        conditions.append("i.id IN (SELECT item_id FROM item_tags WHERE tag LIKE ?)")
        params.append(f"%{tag_hint}%")

    where = " AND ".join(conditions)
    params.append(limit)

    if use_fts:
        sql = f"""SELECT i.* FROM items_fts fts
                  JOIN items i ON i.id = fts.rowid
                  WHERE {where}
                  ORDER BY rank LIMIT ?"""
    else:
        sql = f"""SELECT i.* FROM items i
                  WHERE {where}
                  ORDER BY i.created_at DESC LIMIT ?"""

    cursor = await db.execute(sql, params)
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


# ── Pin / Favorites ────────────────────────────────────────

async def pin_item(db: aiosqlite.Connection, user_id: int, item_id: int) -> bool:
    cursor = await db.execute(
        "UPDATE items SET is_pinned = 1 WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def unpin_item(db: aiosqlite.Connection, user_id: int, item_id: int) -> bool:
    cursor = await db.execute(
        "UPDATE items SET is_pinned = 0 WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_pinned_items(db: aiosqlite.Connection, user_id: int, limit: int = 20) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM items WHERE user_id = ? AND is_pinned = 1 ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


# ── Reading List ───────────────────────────────────────────

async def get_unread_items(db: aiosqlite.Connection, user_id: int, limit: int = 20) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM items WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def mark_item_read(db: aiosqlite.Connection, user_id: int, item_id: int) -> bool:
    cursor = await db.execute(
        "UPDATE items SET is_read = 1 WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


# ── Related Items ───────────────────────────────────────────

async def get_items_with_shared_tags(db: aiosqlite.Connection, user_id: int, item_id: int, min_shared: int = 2, limit: int = 3) -> list[dict]:
    """Find items sharing at least min_shared tags with the given item."""
    cursor = await db.execute(
        """SELECT i.*, COUNT(t2.tag) as shared_count
           FROM item_tags t1
           JOIN item_tags t2 ON t1.tag = t2.tag AND t2.item_id != t1.item_id
           JOIN items i ON i.id = t2.item_id
           WHERE t1.item_id = ? AND i.user_id = ?
           GROUP BY i.id
           HAVING shared_count >= ?
           ORDER BY shared_count DESC
           LIMIT ?""",
        (item_id, user_id, min_shared, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def get_items_in_same_category(db: aiosqlite.Connection, user_id: int, item_id: int, category_id: int, limit: int = 3) -> list[dict]:
    """Find recent items in the same category, excluding the given item."""
    cursor = await db.execute(
        """SELECT * FROM items
           WHERE category_id = ? AND user_id = ? AND id != ?
           ORDER BY created_at DESC LIMIT ?""",
        (category_id, user_id, item_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)
