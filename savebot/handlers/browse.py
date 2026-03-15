"""Browse and search handlers."""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.services.ai_search import parse_search_query, synthesize_answer

router = Router()
PAGE_SIZE = 5


def _format_item(item: dict) -> str:
    tags = " ".join(f"#{t}" for t in item.get("tags", []))
    text = f"<b>#{item['id']}</b> "
    if item.get("ai_summary"):
        text += f"{item['ai_summary']}"
    else:
        text += f"{item['content_text'][:100]}"
    if tags:
        text += f"\n{tags}"
    if item.get("url"):
        text += f"\n🔗 {item['url']}"
    return text


# ── /browse ─────────────────────────────────────────────────

@router.message(Command("browse"))
async def cmd_browse(message: types.Message, db=None):
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await message.reply("Пока нет сохранённых записей. Отправьте мне что-нибудь!")
        return

    buttons = []
    row = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        row.append(InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"browse_cat:{cat['id']}:0",
        ))
        if len(row) == 1:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await message.reply(
        "📂 <b>Категории:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("browse_cat:"))
async def on_browse_category(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    cat_id = int(parts[1])
    offset = int(parts[2])
    user_id = callback.from_user.id

    items = await queries.get_items_by_category(db, user_id, cat_id, limit=PAGE_SIZE, offset=offset)
    total = await queries.count_items_in_category(db, user_id, cat_id)

    if not items:
        await callback.answer("В этой категории пока нет записей.")
        return

    text = "\n\n".join(_format_item(item) for item in items)

    # Pagination buttons
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", callback_data=f"browse_cat:{cat_id}:{offset - PAGE_SIZE}"
        ))
    if offset + PAGE_SIZE < total:
        nav_buttons.append(InlineKeyboardButton(
            text="➡️ Далее", callback_data=f"browse_cat:{cat_id}:{offset + PAGE_SIZE}"
        ))

    buttons = []
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="browse_back")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "browse_back")
async def on_browse_back(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"browse_cat:{cat['id']}:0",
        )])

    await callback.message.edit_text(
        "📂 <b>Категории:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ── /tags ───────────────────────────────────────────────────

@router.message(Command("tags"))
async def cmd_tags(message: types.Message, db=None):
    user_id = message.from_user.id
    tags = await queries.get_all_tags(db, user_id)
    if not tags:
        await message.reply("Тегов пока нет.")
        return

    buttons = []
    row = []
    for t in tags:
        row.append(InlineKeyboardButton(
            text=f"#{t['tag']} ({t['count']})",
            callback_data=f"tag_items:{t['tag']}:0",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await message.reply(
        "🏷 <b>Теги:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("tag_items:"))
async def on_tag_items(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    tag = parts[1]
    offset = int(parts[2])
    user_id = callback.from_user.id

    items = await queries.get_items_by_tag(db, user_id, tag, limit=PAGE_SIZE, offset=offset)
    if not items:
        await callback.answer("Записей с этим тегом нет.")
        return

    text = f"🏷 <b>#{tag}</b>\n\n" + "\n\n".join(_format_item(item) for item in items)

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", callback_data=f"tag_items:{tag}:{offset - PAGE_SIZE}"
        ))
    if len(items) == PAGE_SIZE:
        nav_buttons.append(InlineKeyboardButton(
            text="➡️ Далее", callback_data=f"tag_items:{tag}:{offset + PAGE_SIZE}"
        ))

    buttons = [nav_buttons] if nav_buttons else []
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None,
        parse_mode="HTML",
    )
    await callback.answer()


# ── /search ─────────────────────────────────────────────────

@router.message(Command("search"))
async def cmd_search(message: types.Message, db=None):
    user_id = message.from_user.id
    query = message.text.replace("/search", "", 1).strip()
    if not query:
        await message.reply("Использование: /search <запрос>")
        return

    # Try AI-powered search first
    parsed = await parse_search_query(query)
    items = None
    search_info = ""

    if parsed and parsed.get("keywords"):
        # Show what AI understood
        info_parts = []
        if parsed["keywords"]:
            info_parts.append(f"Ключевые слова: {', '.join(parsed['keywords'])}")
        if parsed.get("date_from"):
            info_parts.append(f"С: {parsed['date_from']}")
        if parsed.get("date_to"):
            info_parts.append(f"До: {parsed['date_to']}")
        if parsed.get("category_hint"):
            info_parts.append(f"Категория: {parsed['category_hint']}")
        if parsed.get("tag_hint"):
            info_parts.append(f"Тег: {parsed['tag_hint']}")
        search_info = "🤖 " + " | ".join(info_parts) + "\n\n"

        # Search with all filters
        items = await queries.search_items_filtered(
            db, user_id,
            keywords=parsed["keywords"],
            date_from=parsed.get("date_from"),
            date_to=parsed.get("date_to"),
            category_hint=parsed.get("category_hint"),
            tag_hint=parsed.get("tag_hint"),
        )

        # Broaden: remove date filters if no results
        if not items and (parsed.get("date_from") or parsed.get("date_to")):
            items = await queries.search_items_filtered(
                db, user_id, keywords=parsed["keywords"],
            )

    # Fallback to basic FTS5
    if not items:
        items = await queries.search_items(db, user_id, query)
        search_info = ""  # Don't show AI info for fallback

    if not items:
        await message.reply(f"🔍 По запросу «{query}» ничего не найдено.")
        return

    text = f"{search_info}🔍 <b>Результаты ({len(items)}):</b>\n\n"
    text += "\n\n".join(_format_item(item) for item in items)
    await message.reply(text, parse_mode="HTML")


@router.message(Command("ask"))
async def cmd_ask(message: types.Message, db=None):
    user_id = message.from_user.id
    question = message.text.replace("/ask", "", 1).strip()
    if not question:
        await message.reply(
            "Использование: /ask <вопрос>\n\n"
            "Примеры:\n"
            "• /ask какие идеи я сохранял про маркетинг?\n"
            "• /ask что я знаю про продуктивность?\n"
            "• /ask резюмируй мои записи про финансы",
        )
        return

    # Find relevant items
    parsed = await parse_search_query(question)
    items = None

    if parsed and parsed.get("keywords"):
        items = await queries.search_items_filtered(
            db, user_id, keywords=parsed["keywords"], limit=15,
        )

    # Fallback: use first 3 words as FTS5 query
    if not items:
        fallback_query = " ".join(question.split()[:3])
        items = await queries.search_items(db, user_id, fallback_query, limit=15)

    if not items:
        await message.reply("🤔 Не нашёл подходящих записей в твоей базе знаний.")
        return

    # Synthesize answer
    answer = await synthesize_answer(question, items)

    if answer:
        text = f"💡 <b>Ответ:</b>\n{answer}\n\n"
        text += f"📚 <b>Источники ({len(items)}):</b>\n"
        for item in items[:5]:
            summary = item.get("ai_summary") or item["content_text"][:60]
            text += f"  #{item['id']} {summary}\n"
    else:
        # AI failed — show search results instead
        text = "🔍 Не удалось сформировать ответ, но вот подходящие записи:\n\n"
        text += "\n\n".join(_format_item(item) for item in items[:10])

    await message.reply(text, parse_mode="HTML")


# ── /recent ─────────────────────────────────────────────────

@router.message(Command("recent"))
async def cmd_recent(message: types.Message, db=None):
    user_id = message.from_user.id
    items = await queries.get_recent_items(db, user_id, limit=10)
    if not items:
        await message.reply("Пока нет сохранённых записей.")
        return

    text = "🕐 <b>Последние записи:</b>\n\n"
    text += "\n\n".join(_format_item(item) for item in items)
    await message.reply(text, parse_mode="HTML")
