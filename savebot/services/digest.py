"""Weekly digest and daily brief generation."""
from __future__ import annotations
import logging
from html import escape

from savebot.db import queries
from savebot.services.connections import find_related_items

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


def _item_line(item: dict) -> str:
    """Format a single item as a one-liner for the daily brief."""
    summary = item.get("ai_summary") or item.get("content_text", "")
    summary = escape(summary[:80])
    cat_emoji = item.get("category_emoji") or "📁"
    return f"  {cat_emoji} {summary}"


async def generate_daily_brief(db, user_id: int) -> str | None:
    """Generate daily brief HTML text. Returns None if nothing to show."""
    parts = ["<b>🧠 Твой Daily Brief</b>\n"]
    has_content = False

    # Section 1: Related to yesterday's items
    try:
        yesterday_items = await queries.get_items_saved_yesterday(db, user_id)
        if yesterday_items:
            related_lines = []
            for item in yesterday_items[:5]:
                related = await find_related_items(
                    db,
                    item_id=item["id"],
                    user_id=user_id,
                    category_id=item.get("category_id"),
                    tags=item.get("tags", []),
                    top_k=2,
                )
                if related:
                    summary = item.get("ai_summary") or item.get("content_text", "")
                    related_lines.append(f"  📎 <i>{escape(summary[:50])}</i>:")
                    for rel in related[:2]:
                        related_lines.append(_item_line(rel))
            if related_lines:
                parts.append("<b>📎 Связано с вчерашним</b>")
                parts.extend(related_lines)
                parts.append("")
                has_content = True
    except Exception as e:
        logger.warning("Daily brief: related section failed: %s", e)

    # Section 2: Forgotten items
    try:
        forgotten = await queries.get_items_page_with_nums(db, user_id, "forgotten", limit=3, offset=0)
        if forgotten:
            parts.append("<b>🕸 Пора вспомнить</b>")
            for item in forgotten:
                parts.append(_item_line(item))
            parts.append("")
            has_content = True
    except Exception as e:
        logger.warning("Daily brief: forgotten section failed: %s", e)

    # Section 3: On this day in past years
    try:
        on_this_day = await queries.get_items_on_this_day(db, user_id)
        if on_this_day:
            parts.append("<b>📅 В этот день</b>")
            for item in on_this_day:
                year = (item.get("created_at") or "")[:4]
                line = _item_line(item)
                if year:
                    line += f"  <i>({year})</i>"
                parts.append(line)
            parts.append("")
            has_content = True
    except Exception as e:
        logger.warning("Daily brief: on-this-day section failed: %s", e)

    # Section 4: Inbox count
    try:
        inbox_count = await queries.get_inbox_count(db, user_id)
        if inbox_count > 0:
            parts.append(f"<b>📥 Inbox:</b> У тебя {inbox_count} записей в Inbox")
            parts.append("")
            has_content = True
    except Exception as e:
        logger.warning("Daily brief: inbox section failed: %s", e)

    # Section 5: Weekly category stats
    try:
        cat_stats = await queries.get_weekly_category_stats(db, user_id)
        if cat_stats:
            stat_parts = [f"{s['count']} в {s['emoji']} {s['name']}" for s in cat_stats[:5]]
            parts.append(f"<b>📊 Тема недели:</b> {', '.join(stat_parts)}")
            has_content = True
    except Exception as e:
        logger.warning("Daily brief: stats section failed: %s", e)

    if not has_content:
        return None

    return "\n".join(parts)


async def send_daily_brief(bot, db, user_id: int) -> bool:
    """Generate and send daily brief to a user. Returns True if sent."""
    try:
        text = await generate_daily_brief(db, user_id)
        if text:
            await bot.send_message(user_id, text, parse_mode="HTML")
            logger.info("Daily brief sent to user %s", user_id)
            return True
        logger.debug("Daily brief empty for user %s, skipping", user_id)
        return False
    except Exception as e:
        logger.error("Failed to send daily brief to user %s: %s", user_id, e)
        return False
