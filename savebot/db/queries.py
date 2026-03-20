"""Database query functions.

Sections and key functions:
─────────────────────────────────────────────────
Lines ~11-13   Allowed preference keys (_ALLOWED_PREF_KEYS)
Lines ~16-23   Helper: _attach_tags
Lines ~26-50   Default categories: DEFAULT_CATEGORIES, ensure_default_categories
Lines ~53-119  Categories: get_or_create_category, get_or_create_inbox_category,
               get_category_by_name, get_all_categories, rename_category,
               delete_category, merge_categories
Lines ~122-278 Items: save_item, get_item, get_items_by_category, get_items_by_tag,
               search_items, get_recent_items, update_item_category,
               update_item_tags, update_item_note, delete_item, find_duplicate
Lines ~281-293 Tags: get_all_tags
Lines ~296-308 Stats: get_stats
Lines ~311-346 Export & counts: export_all, count_items_by_category,
               count_items_in_category
Lines ~349-369 User preferences: get_user_preferences, update_user_preference
Lines ~372-443 Weekly/Digest: get_items_this_week, get_items_on_this_week,
               get_weekly_stats, get_all_users_with_digest, log_digest, _escape_fts5
Lines ~445-498 Filtered search: search_items_filtered
Lines ~501-525 Pin/Favorites: pin_item, unpin_item, get_pinned_items
Lines ~528-549 Sources: get_all_sources, count_items_by_source
Lines ~552-637 Knowledge map & related: get_category_tag_map, get_forgotten_items,
               get_items_with_shared_tags, get_items_in_same_category,
               get_similar_items_fts
Lines ~640-740 Collections: create_collection, get_collections, get_collection_items,
               add_to_collection, remove_from_collection, delete_collection,
               count_collection_items
Lines ~743-860 Navigation: _context_sql, get_adjacent_item_ids,
               get_items_page_with_nums, count_items_by_tag, create_category_manual
Lines ~863-923 Daily brief: get_items_saved_yesterday, get_items_on_this_day,
               get_weekly_category_stats, get_inbox_count,
               get_all_users_with_daily_brief
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite


# ── Allowed preference keys (whitelist for SQL injection prevention) ──

_ALLOWED_PREF_KEYS = {"auto_save", "digest_enabled", "digest_day", "digest_time", "language", "daily_brief_enabled", "daily_brief_time"}


# ── Helper ─────────────────────────────────────────────────

async def _attach_tags(db: aiosqlite.Connection, items: list[dict]) -> list[dict]:
    """Attach tags to a list of items in one batch query."""
    if not items:
        return items
    ids = [item["id"] for item in items]
    placeholders = ",".join("?" * len(ids))
    cursor = await db.execute(
        f"SELECT item_id, tag FROM item_tags WHERE item_id IN ({placeholders})", ids,
    )
    rows = await cursor.fetchall()
    tag_map: dict[int, list[str]] = {}
    for row in rows:
        tag_map.setdefault(row["item_id"], []).append(row["tag"])
    for item in items:
        item["tags"] = tag_map.get(item["id"], [])
    return items


# ── Default Categories ─────────────────────────────────────

DEFAULT_CATEGORIES = [
    ("Технологии", "💻"),
    ("Финансы", "💰"),
    ("Здоровье", "🏋️"),
    ("Обучение", "📚"),
    ("Работа", "🏢"),
    ("Творчество", "🎨"),
    ("Разное", "📥"),
]


# ── Sort Options ──────────────────────────────────────────
SORT_OPTIONS = {
    "d": "i.created_at DESC",
    "p": "i.is_pinned DESC, i.created_at DESC",
    "a": "COALESCE(i.ai_summary, i.content_text) ASC",
    "s": "CASE WHEN i.source IS NULL THEN 1 ELSE 0 END, i.source ASC, i.created_at DESC",
    "o": "i.created_at ASC",
}


async def ensure_default_categories(db: aiosqlite.Connection, user_id: int) -> None:
    """Create 7 default categories if user has none. Safe to call on every save."""
    try:
        cursor = await db.execute("SELECT COUNT(*) as c FROM categories WHERE user_id = ?", (user_id,))
        count = (await cursor.fetchone())["c"]
        if count > 0:
            return
        for name, emoji in DEFAULT_CATEGORIES:
            await get_or_create_category(db, user_id, name, emoji)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("ensure_default_categories failed for user %d", user_id, exc_info=True)


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


async def get_or_create_inbox_category(db: aiosqlite.Connection, user_id: int) -> dict:
    """Get or create the special 'Inbox' category for quick capture."""
    return await get_or_create_category(db, user_id, "Inbox", "📥")


async def get_category_by_name(db: aiosqlite.Connection, user_id: int, name: str) -> dict | None:
    """Get a category by exact name match."""
    cursor = await db.execute(
        "SELECT * FROM categories WHERE name = ? AND user_id = ?", (name, user_id)
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


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


async def delete_empty_non_default_categories(db: aiosqlite.Connection, user_id: int) -> int:
    """Delete categories with 0 items, keeping the 7 defaults."""
    default_names = [name for name, _ in DEFAULT_CATEGORIES]
    placeholders = ",".join("?" * len(default_names))
    cursor = await db.execute(
        f"""DELETE FROM categories
            WHERE user_id = ?
            AND name NOT IN ({placeholders})
            AND id NOT IN (
                SELECT DISTINCT category_id FROM items
                WHERE category_id IS NOT NULL AND user_id = ?
            )""",
        [user_id] + default_names + [user_id],
    )
    await db.commit()
    return cursor.rowcount


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
    forward_url: str | None = None,
) -> int:
    cursor = await db.execute(
        """INSERT INTO items (category_id, content_type, content_text, url, file_id, source, ai_summary, tg_message_id, user_id, forward_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (category_id, content_type, content_text, url, file_id, source, ai_summary, tg_message_id, user_id, forward_url),
    )
    item_id = cursor.lastrowid
    for tag in tags:
        await db.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag.replace("-", "_")),
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
            (item_id, tag.replace("-", "_")),
        )
    await db.commit()


async def update_item_note(db: aiosqlite.Connection, user_id: int, item_id: int, note: str) -> bool:
    cursor = await db.execute(
        "UPDATE items SET user_note = ? WHERE id = ? AND user_id = ?", (note, item_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_item(db: aiosqlite.Connection, user_id: int, item_id: int) -> bool:
    cursor = await db.execute("DELETE FROM items WHERE id = ? AND user_id = ?", (item_id, user_id))
    await db.commit()
    return cursor.rowcount > 0


async def find_duplicate(
    db: aiosqlite.Connection, user_id: int, content_text: str,
    url: str | None = None, forward_url: str | None = None, tg_message_id: int | None = None,
) -> dict | None:
    # Check forward_url first (most specific for forwarded posts)
    if forward_url:
        cursor = await db.execute(
            "SELECT * FROM items WHERE forward_url = ? AND user_id = ?", (forward_url, user_id)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
    # Check tg_message_id
    if tg_message_id:
        cursor = await db.execute(
            "SELECT * FROM items WHERE tg_message_id = ? AND user_id = ?", (tg_message_id, user_id)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
    # Existing checks
    if url:
        cursor = await db.execute("SELECT * FROM items WHERE url = ? AND user_id = ?", (url, user_id))
        row = await cursor.fetchone()
        if row:
            return dict(row)
    if content_text:
        cursor = await db.execute("SELECT * FROM items WHERE content_text = ? AND user_id = ?", (content_text, user_id))
        row = await cursor.fetchone()
        if row:
            return dict(row)
    return None


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


async def count_items_by_category(db: aiosqlite.Connection, user_id: int, category_id: int | None = None) -> int:
    """Count items without loading them all into memory."""
    if category_id:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = ? AND category_id = ?",
            (user_id, category_id),
        )
    else:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM items WHERE user_id = ?",
            (user_id,),
        )
    row = await cursor.fetchone()
    return row[0]


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
    return {"user_id": user_id, "auto_save": 1, "digest_enabled": 1, "digest_day": 1, "digest_time": "10:00", "language": "ru", "daily_brief_enabled": 0, "daily_brief_time": "09:00"}


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


# ── Sources (channels) ─────────────────────────────────────

async def get_all_sources(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Get distinct sources with item counts, ordered by count DESC."""
    cursor = await db.execute(
        """SELECT source, COUNT(*) as count
           FROM items
           WHERE user_id = ? AND source IS NOT NULL AND source != ''
           GROUP BY source
           ORDER BY count DESC""",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def count_items_by_source(db: aiosqlite.Connection, user_id: int, source: str) -> int:
    """Count items from a specific source."""
    cursor = await db.execute(
        "SELECT COUNT(*) AS c FROM items WHERE user_id = ? AND source = ?",
        (user_id, source),
    )
    return (await cursor.fetchone())["c"]


async def get_sources_by_category(
    db: aiosqlite.Connection, user_id: int, category_id: int
) -> list[dict]:
    """Get distinct sources with item counts for a specific category."""
    cursor = await db.execute(
        """SELECT source, COUNT(*) as count
           FROM items
           WHERE user_id = ? AND category_id = ? AND source IS NOT NULL AND source != ''
           GROUP BY source
           ORDER BY count DESC""",
        (user_id, category_id),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_all_sources_by_date(
    db: aiosqlite.Connection, user_id: int, ascending: bool = False
) -> list[dict]:
    """Get distinct sources sorted by date of most recent item."""
    order = "ASC" if ascending else "DESC"
    cursor = await db.execute(
        f"""SELECT source, COUNT(*) as count, MAX(created_at) as last_saved
            FROM items
            WHERE user_id = ? AND source IS NOT NULL AND source != ''
            GROUP BY source
            ORDER BY last_saved {order}""",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


# ── Knowledge Map ──────────────────────────────────────────

async def get_category_tag_map(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Get categories with their top tags for the knowledge map."""
    categories = await get_all_categories(db, user_id)
    for cat in categories:
        cursor = await db.execute(
            """SELECT t.tag, COUNT(*) as cnt
               FROM item_tags t JOIN items i ON i.id = t.item_id
               WHERE i.category_id = ? AND i.user_id = ?
               GROUP BY t.tag ORDER BY cnt DESC LIMIT 5""",
            (cat["id"], user_id),
        )
        cat["top_tags"] = [r["tag"] for r in await cursor.fetchall()]
    return categories


async def get_forgotten_items(db: aiosqlite.Connection, user_id: int, days: int = 30, limit: int = 10) -> list[dict]:
    """Items older than N days, not pinned, oldest first."""
    cursor = await db.execute(
        """SELECT * FROM items
           WHERE user_id = ? AND is_pinned = 0
             AND created_at < datetime('now', ?)
           ORDER BY created_at ASC LIMIT ?""",
        (user_id, f"-{days} days", limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


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


async def get_similar_items_fts(db: aiosqlite.Connection, user_id: int, item_id: int, limit: int = 5) -> list[dict]:
    """Find similar items via FTS5 using the first 3 words of ai_summary."""
    cursor = await db.execute(
        "SELECT ai_summary FROM items WHERE id = ? AND user_id = ?",
        (item_id, user_id),
    )
    row = await cursor.fetchone()
    if not row or not row["ai_summary"]:
        return []

    words = row["ai_summary"].split()[:3]
    fts_query = _escape_fts5(words)
    if not fts_query:
        return []

    cursor = await db.execute(
        """SELECT i.* FROM items_fts fts
           JOIN items i ON i.id = fts.rowid
           WHERE items_fts MATCH ? AND i.user_id = ? AND i.id != ?
           ORDER BY rank LIMIT ?""",
        (fts_query, user_id, item_id, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


# ── Collections ───────────────────────────────────────────

async def create_collection(db: aiosqlite.Connection, user_id: int, name: str, emoji: str = "\U0001f4c1") -> dict:
    """Create a new collection for the user."""
    cursor = await db.execute(
        "INSERT INTO collections (user_id, name, emoji) VALUES (?, ?, ?)",
        (user_id, name, emoji),
    )
    await db.commit()
    return {"id": cursor.lastrowid, "name": name, "user_id": user_id, "emoji": emoji}


async def get_collections(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Get all collections for the user with item counts."""
    cursor = await db.execute(
        """SELECT c.*, COUNT(ci.item_id) as item_count
           FROM collections c
           LEFT JOIN collection_items ci ON ci.collection_id = c.id
           WHERE c.user_id = ?
           GROUP BY c.id
           ORDER BY c.created_at DESC""",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_collection_items(
    db: aiosqlite.Connection, user_id: int, collection_id: int, limit: int = 5, offset: int = 0
) -> list[dict]:
    """Get items in a collection with tags attached."""
    cursor = await db.execute(
        """SELECT i.* FROM items i
           JOIN collection_items ci ON ci.item_id = i.id
           WHERE ci.collection_id = ? AND i.user_id = ?
           ORDER BY ci.added_at DESC LIMIT ? OFFSET ?""",
        (collection_id, user_id, limit, offset),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def add_to_collection(db: aiosqlite.Connection, user_id: int, collection_id: int, item_id: int) -> bool:
    """Add an item to a collection. Returns False if already in collection."""
    # Verify both belong to user
    coll = await db.execute(
        "SELECT id FROM collections WHERE id = ? AND user_id = ?", (collection_id, user_id)
    )
    if not await coll.fetchone():
        return False
    item = await db.execute(
        "SELECT id FROM items WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    if not await item.fetchone():
        return False

    try:
        await db.execute(
            "INSERT INTO collection_items (collection_id, item_id) VALUES (?, ?)",
            (collection_id, item_id),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_from_collection(db: aiosqlite.Connection, user_id: int, collection_id: int, item_id: int) -> bool:
    """Remove an item from a collection."""
    # Verify collection belongs to user
    coll = await db.execute(
        "SELECT id FROM collections WHERE id = ? AND user_id = ?", (collection_id, user_id)
    )
    if not await coll.fetchone():
        return False

    cursor = await db.execute(
        "DELETE FROM collection_items WHERE collection_id = ? AND item_id = ?",
        (collection_id, item_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_collection(db: aiosqlite.Connection, user_id: int, collection_id: int) -> bool:
    """Delete a collection (items themselves are not deleted)."""
    cursor = await db.execute(
        "DELETE FROM collections WHERE id = ? AND user_id = ?", (collection_id, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def count_collection_items(db: aiosqlite.Connection, user_id: int, collection_id: int) -> int:
    """Count items in a collection belonging to the user."""
    cursor = await db.execute(
        """SELECT COUNT(*) as c FROM collection_items ci
           JOIN items i ON i.id = ci.item_id
           WHERE ci.collection_id = ? AND i.user_id = ?""",
        (collection_id, user_id),
    )
    return (await cursor.fetchone())["c"]


# ── Navigation ─────────────────────────────────────────────

def _context_sql(context_type: str, context_id: str | int | None, sort_by: str = "d") -> tuple[str, list, str]:
    """Return (WHERE clause, params, ORDER BY) for a given context type."""
    if context_type == "category":
        order = SORT_OPTIONS.get(sort_by, SORT_OPTIONS["d"])
        return "i.category_id = ? AND i.user_id = ?", [context_id], order
    elif context_type == "tag":
        return (
            "i.id IN (SELECT item_id FROM item_tags WHERE tag = ?) AND i.user_id = ?",
            [context_id],
            "i.created_at DESC",
        )
    elif context_type == "recent":
        order = SORT_OPTIONS.get(sort_by, SORT_OPTIONS["d"])
        return "i.user_id = ?", [], order
    elif context_type == "pinned":
        return "i.is_pinned = 1 AND i.user_id = ?", [], "i.created_at DESC"
    elif context_type == "forgotten":
        return (
            "i.is_pinned = 0 AND i.created_at < datetime('now', '-30 days') AND i.user_id = ?",
            [],
            "i.created_at ASC",
        )
    elif context_type == "collection":
        return (
            "i.id IN (SELECT item_id FROM collection_items WHERE collection_id = ?) AND i.user_id = ?",
            [context_id],
            "i.created_at DESC",
        )
    elif context_type == "source":
        return "i.source = ? AND i.user_id = ?", [context_id], "i.created_at DESC"
    else:
        raise ValueError(f"Unknown context_type: {context_type}")


async def get_adjacent_item_ids(
    db: aiosqlite.Connection,
    user_id: int,
    item_id: int,
    context_type: str,
    context_id: str | int | None = None,
    sort_by: str = "d",
) -> dict | None:
    """Return {prev_id, next_id, position, total} for an item within a browsing context."""
    where, extra_params, order = _context_sql(context_type, context_id, sort_by=sort_by)
    params = extra_params + [user_id]

    cursor = await db.execute(
        f"""WITH ctx AS (
                SELECT i.id,
                       LAG(i.id) OVER (ORDER BY {order}) AS prev_id,
                       LEAD(i.id) OVER (ORDER BY {order}) AS next_id,
                       ROW_NUMBER() OVER (ORDER BY {order}) AS position,
                       COUNT(*) OVER () AS total
                FROM items i
                WHERE {where}
            )
            SELECT * FROM ctx WHERE id = ?""",
        params + [item_id],
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return dict(row)


async def get_items_page_with_nums(
    db: aiosqlite.Connection,
    user_id: int,
    context_type: str,
    context_id: str | int | None = None,
    limit: int = 5,
    offset: int = 0,
    sort_by: str = "d",
) -> list[dict]:
    """Return items with display_num for clickable list view, including category info."""
    where, extra_params, order = _context_sql(context_type, context_id, sort_by=sort_by)
    params = extra_params + [user_id, limit, offset]

    cursor = await db.execute(
        f"""SELECT sub.*, c.name AS category_name, c.emoji AS category_emoji
            FROM (
                SELECT i.*,
                       ROW_NUMBER() OVER (ORDER BY {order}) AS display_num
                FROM items i
                WHERE {where}
            ) sub
            LEFT JOIN categories c ON c.id = sub.category_id
            ORDER BY sub.display_num
            LIMIT ? OFFSET ?""",
        params,
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def count_items_by_tag(db: aiosqlite.Connection, user_id: int, tag: str) -> int:
    """Exact count of items with a given tag."""
    cursor = await db.execute(
        """SELECT COUNT(*) AS c FROM item_tags t
           JOIN items i ON i.id = t.item_id
           WHERE t.tag = ? AND i.user_id = ?""",
        (tag, user_id),
    )
    return (await cursor.fetchone())["c"]


async def count_items_in_context(
    db: aiosqlite.Connection,
    user_id: int,
    context_type: str,
    context_id: str | int | None = None,
) -> int:
    """Count items in a browsing context without loading them."""
    where, extra_params, _order = _context_sql(context_type, context_id)
    params = extra_params + [user_id]
    cursor = await db.execute(
        f"SELECT COUNT(*) AS c FROM items i WHERE {where}", params,
    )
    return (await cursor.fetchone())["c"]


async def create_category_manual(
    db: aiosqlite.Connection, user_id: int, name: str, emoji: str = "\U0001f4c1"
) -> dict:
    """Create a category, raising ValueError if a duplicate name exists for this user."""
    cursor = await db.execute(
        "SELECT * FROM categories WHERE name = ? AND user_id = ?", (name, user_id)
    )
    if await cursor.fetchone():
        raise ValueError(f"Category '{name}' already exists")
    cursor = await db.execute(
        "INSERT INTO categories (name, user_id, emoji) VALUES (?, ?, ?)", (name, user_id, emoji)
    )
    await db.commit()
    return {"id": cursor.lastrowid, "name": name, "user_id": user_id, "emoji": emoji}


# ── Daily Brief ────────────────────────────────────────────

async def get_items_saved_yesterday(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Items saved in the last 24 hours."""
    cursor = await db.execute(
        """SELECT i.*, c.name AS category_name, c.emoji AS category_emoji
           FROM items i LEFT JOIN categories c ON c.id = i.category_id
           WHERE i.user_id = ? AND i.created_at >= datetime('now', '-1 day')
           ORDER BY i.created_at DESC""",
        (user_id,),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def get_items_on_this_day(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Items saved on the same month+day in previous years (anniversary items)."""
    cursor = await db.execute(
        """SELECT i.*, c.name AS category_name, c.emoji AS category_emoji
           FROM items i LEFT JOIN categories c ON c.id = i.category_id
           WHERE i.user_id = ?
             AND strftime('%m-%d', i.created_at) = strftime('%m-%d', 'now')
             AND strftime('%Y', i.created_at) < strftime('%Y', 'now')
           ORDER BY i.created_at DESC""",
        (user_id,),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    return await _attach_tags(db, items)


async def get_weekly_category_stats(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    """Categories with most new items this week, returns list of {name, emoji, count}."""
    cursor = await db.execute(
        """SELECT c.name, c.emoji, COUNT(i.id) AS count
           FROM items i
           JOIN categories c ON c.id = i.category_id
           WHERE i.user_id = ? AND i.created_at >= datetime('now', '-7 days')
           GROUP BY c.id
           ORDER BY count DESC""",
        (user_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def get_inbox_count(db: aiosqlite.Connection, user_id: int) -> int:
    """Count of items in the Inbox category."""
    cursor = await db.execute(
        """SELECT COUNT(*) AS c FROM items i
           JOIN categories cat ON cat.id = i.category_id
           WHERE i.user_id = ? AND cat.name = 'Inbox' AND cat.user_id = ?""",
        (user_id, user_id),
    )
    return (await cursor.fetchone())["c"]


async def get_all_users_with_daily_brief(db: aiosqlite.Connection) -> list[dict]:
    """Get all users who have daily brief enabled."""
    cursor = await db.execute(
        "SELECT * FROM user_preferences WHERE daily_brief_enabled = 1"
    )
    return [dict(r) for r in await cursor.fetchall()]
