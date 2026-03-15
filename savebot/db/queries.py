"""Database query functions."""

from __future__ import annotations

import json
from typing import Any

import aiosqlite


# ── Categories ──────────────────────────────────────────────

async def get_or_create_category(db: aiosqlite.Connection, name: str, emoji: str = "📁") -> dict:
    cursor = await db.execute("SELECT * FROM categories WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row:
        return dict(row)
    cursor = await db.execute(
        "INSERT INTO categories (name, emoji) VALUES (?, ?)", (name, emoji)
    )
    await db.commit()
    return {"id": cursor.lastrowid, "name": name, "emoji": emoji}


async def get_all_categories(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        """SELECT c.*, COUNT(i.id) as item_count
           FROM categories c
           LEFT JOIN items i ON i.category_id = c.id
           GROUP BY c.id
           ORDER BY item_count DESC"""
    )
    return [dict(r) for r in await cursor.fetchall()]


async def rename_category(db: aiosqlite.Connection, cat_id: int, new_name: str) -> bool:
    cursor = await db.execute(
        "UPDATE categories SET name = ? WHERE id = ?", (new_name, cat_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_category(db: aiosqlite.Connection, cat_id: int) -> int:
    cursor = await db.execute(
        "UPDATE items SET category_id = NULL WHERE category_id = ?", (cat_id,)
    )
    affected = cursor.rowcount
    await db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    await db.commit()
    return affected


async def merge_categories(db: aiosqlite.Connection, source_id: int, target_id: int) -> int:
    cursor = await db.execute(
        "UPDATE items SET category_id = ? WHERE category_id = ?", (target_id, source_id)
    )
    affected = cursor.rowcount
    await db.execute("DELETE FROM categories WHERE id = ?", (source_id,))
    await db.commit()
    return affected


# ── Items ───────────────────────────────────────────────────

async def save_item(
    db: aiosqlite.Connection,
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
        """INSERT INTO items (category_id, content_type, content_text, url, file_id, source, ai_summary, tg_message_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (category_id, content_type, content_text, url, file_id, source, ai_summary, tg_message_id),
    )
    item_id = cursor.lastrowid
    for tag in tags:
        await db.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )
    await db.commit()
    return item_id


async def get_item(db: aiosqlite.Connection, item_id: int) -> dict | None:
    cursor = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    item = dict(row)
    cursor = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item_id,))
    item["tags"] = [r["tag"] for r in await cursor.fetchall()]
    return item


async def get_items_by_category(
    db: aiosqlite.Connection, category_id: int, limit: int = 5, offset: int = 0
) -> list[dict]:
    cursor = await db.execute(
        """SELECT * FROM items WHERE category_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (category_id, limit, offset),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


async def get_items_by_tag(
    db: aiosqlite.Connection, tag: str, limit: int = 5, offset: int = 0
) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.* FROM items i
           JOIN item_tags t ON t.item_id = i.id
           WHERE t.tag = ?
           ORDER BY i.created_at DESC LIMIT ? OFFSET ?""",
        (tag, limit, offset),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


async def search_items(db: aiosqlite.Connection, query: str, limit: int = 10) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.*, highlight(items_fts, 0, '<b>', '</b>') as highlighted
           FROM items_fts fts
           JOIN items i ON i.id = fts.rowid
           WHERE items_fts MATCH ?
           ORDER BY rank
           LIMIT ?""",
        (query, limit),
    )
    items = [dict(r) for r in await cursor.fetchall()]
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


async def get_recent_items(db: aiosqlite.Connection, limit: int = 10) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM items ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    items = [dict(r) for r in await cursor.fetchall()]
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


async def update_item_category(db: aiosqlite.Connection, item_id: int, category_id: int) -> bool:
    cursor = await db.execute(
        "UPDATE items SET category_id = ? WHERE id = ?", (category_id, item_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_item_tags(db: aiosqlite.Connection, item_id: int, tags: list[str]) -> None:
    await db.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
    for tag in tags:
        await db.execute(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )
    await db.commit()


async def delete_item(db: aiosqlite.Connection, item_id: int) -> bool:
    cursor = await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
    await db.commit()
    return cursor.rowcount > 0


async def find_duplicate(db: aiosqlite.Connection, content_text: str, url: str | None = None) -> dict | None:
    if url:
        cursor = await db.execute("SELECT * FROM items WHERE url = ?", (url,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
    cursor = await db.execute("SELECT * FROM items WHERE content_text = ?", (content_text,))
    row = await cursor.fetchone()
    return dict(row) if row else None


# ── Tags ────────────────────────────────────────────────────

async def get_all_tags(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        """SELECT tag, COUNT(*) as count
           FROM item_tags
           GROUP BY tag
           ORDER BY count DESC"""
    )
    return [dict(r) for r in await cursor.fetchall()]


# ── Stats ───────────────────────────────────────────────────

async def get_stats(db: aiosqlite.Connection) -> dict:
    items = await db.execute("SELECT COUNT(*) as c FROM items")
    items_count = (await items.fetchone())["c"]
    cats = await db.execute("SELECT COUNT(*) as c FROM categories")
    cats_count = (await cats.fetchone())["c"]
    tags = await db.execute("SELECT COUNT(DISTINCT tag) as c FROM item_tags")
    tags_count = (await tags.fetchone())["c"]
    return {"items": items_count, "categories": cats_count, "tags": tags_count}


# ── Export ──────────────────────────────────────────────────

async def export_all(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        """SELECT i.*, c.name as category_name, c.emoji as category_emoji
           FROM items i
           LEFT JOIN categories c ON c.id = i.category_id
           ORDER BY i.created_at DESC"""
    )
    items = [dict(r) for r in await cursor.fetchall()]
    for item in items:
        c = await db.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item["id"],))
        item["tags"] = [r["tag"] for r in await c.fetchall()]
    return items


async def count_items_in_category(db: aiosqlite.Connection, category_id: int) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) as c FROM items WHERE category_id = ?", (category_id,)
    )
    return (await cursor.fetchone())["c"]
