"""Find related items by shared tags, category, or source."""
from __future__ import annotations
import logging
from savebot.db import queries

logger = logging.getLogger(__name__)

async def find_related_items(db, item_id: int, user_id: int, category_id: int | None, tags: list[str], source: str | None = None, top_k: int = 3) -> list[dict]:
    """Find items related to the given item."""
    related = []
    seen_ids = {item_id}

    # 1. Items sharing 2+ tags
    if tags:
        shared = await queries.get_items_with_shared_tags(db, user_id, item_id, min_shared=1, limit=top_k)
        for item in shared:
            if item["id"] not in seen_ids:
                related.append(item)
                seen_ids.add(item["id"])

    # 2. Items in same category
    if len(related) < top_k and category_id:
        same_cat = await queries.get_items_in_same_category(db, user_id, item_id, category_id, limit=top_k)
        for item in same_cat:
            if item["id"] not in seen_ids:
                related.append(item)
                seen_ids.add(item["id"])
                if len(related) >= top_k:
                    break

    # 3. FTS5 similarity by ai_summary
    if len(related) < top_k:
        fts_items = await queries.get_similar_items_fts(db, user_id, item_id, limit=top_k)
        for item in fts_items:
            if item["id"] not in seen_ids:
                related.append(item)
                seen_ids.add(item["id"])
                if len(related) >= top_k:
                    break

    return related[:top_k]
