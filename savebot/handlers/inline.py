"""Inline mode handler — search knowledge base from any chat."""
from __future__ import annotations

import logging
from hashlib import md5

from aiogram import Router, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

from savebot.db import queries

logger = logging.getLogger(__name__)
router = Router()


@router.inline_query()
async def on_inline_query(inline_query: types.InlineQuery, db=None):
    """Handle inline queries: @BotName <search query>."""
    user_id = inline_query.from_user.id
    query = inline_query.query.strip()

    if not query:
        # Empty query — show recent items
        items = await queries.get_recent_items(db, user_id, limit=10)
    else:
        # Search by query
        items = await queries.search_items(db, user_id, query, limit=10)

    results = []
    for item in items:
        title = item.get("ai_summary") or item["content_text"][:80]
        description = " ".join(f"#{t}" for t in item.get("tags", []))
        content = item["content_text"][:4000]
        if item.get("url"):
            content += f"\n\n🔗 {item['url']}"

        result_id = md5(f"{item['id']}".encode()).hexdigest()
        results.append(
            InlineQueryResultArticle(
                id=result_id,
                title=title,
                description=description or "Без тегов",
                input_message_content=InputTextMessageContent(
                    message_text=content,
                ),
            )
        )

    await inline_query.answer(results, cache_time=10, is_personal=True)
