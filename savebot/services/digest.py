"""Weekly digest generation."""
from __future__ import annotations
import logging
from savebot.db import queries

logger = logging.getLogger(__name__)

async def generate_weekly_digest(db, user_id: int) -> str | None:
    """Generate weekly digest for a user. Returns formatted HTML text or None if nothing to report."""
    stats = await queries.get_weekly_stats(db, user_id)
    week_items = await queries.get_items_this_week(db, user_id, limit=20)
    on_this_week = await queries.get_items_on_this_week(db, user_id, limit=5)

    if not week_items and not on_this_week:
        return None

    parts = ["<b>📬 Недельный дайджест</b>\n"]

    # Section 1: Saved this week
    if week_items:
        parts.append(f"\n<b>📝 Сохранено за неделю ({stats['week_items']})</b>")
        # Group by category
        by_category = {}
        for item in week_items:
            cat_name = item.get("category_name") or "Без категории"
            cat_emoji = item.get("category_emoji") or "📁"
            key = f"{cat_emoji} {cat_name}"
            if key not in by_category:
                by_category[key] = []
            by_category[key].append(item)

        for cat, items in by_category.items():
            summaries = []
            for it in items[:3]:  # max 3 per category
                summary = it.get("ai_summary") or it["content_text"][:60]
                summaries.append(f"  • {summary}")
            if len(items) > 3:
                summaries.append(f"  <i>...и ещё {len(items) - 3}</i>")
            parts.append(f"\n{cat}:")
            parts.extend(summaries)

    # Section 2: On This Day
    if on_this_week:
        parts.append(f"\n\n<b>📅 В это время ранее</b>")
        for item in on_this_week:
            saved_at = item.get("saved_at", item.get("created_at", ""))
            summary = item.get("ai_summary") or item["content_text"][:60]
            cat_emoji = item.get("category_emoji") or "📁"
            parts.append(f"  {cat_emoji} {summary}")
            if saved_at:
                parts.append(f"     <i>сохранено {saved_at[:10]}</i>")

    # Section 3: Stats
    parts.append(f"\n\n<b>📊 Итого</b>")
    parts.append(f"Всего записей: {stats['total_items']}")
    parts.append(f"За эту неделю: +{stats['week_items']}")
    parts.append(f"Категорий: {stats['categories']} | Тегов: {stats['tags']}")

    return "\n".join(parts)
