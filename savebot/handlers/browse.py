"""Browse and search handlers."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.db.state_store import set_state
from savebot.handlers.browse_core import (
    PAGE_SIZE, _CTX_MAP, _CTX_REV, _CTX_TITLES, SORT_LABELS,
    _truncate_tag, _truncate_source, _format_item_short, _format_item_full,
    _format_item, _sort_buttons, _recent_sort_buttons, _clickable_list_buttons,
    _back_button_for_ctx, _categories_markup, _more_markup,
    _show_list, _show_item_view, _show_collections, _show_categories_msg,
    _extract_list_context,
)
from savebot.services.ai_search import parse_search_query
from savebot.services.connections import find_related_items

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("browse"))
async def cmd_browse(message: types.Message, db=None):
    await _show_categories_msg(message, db=db)


@router.callback_query(F.data == "bm:hub")
async def on_hub(callback: types.CallbackQuery, db=None):
    await callback.message.edit_text(
        "📋 <b>Ещё</b>",
        reply_markup=_more_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Hub: Categories ────────────────────────────────────────

@router.callback_query(F.data == "bm:cats")
async def on_hub_cats(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await callback.message.edit_text(
            "📂 <b>Записей пока нет.</b>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📂 <b>Все записи:</b>",
        reply_markup=_categories_markup(categories),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Category Sub-Menu ─────────────────────────────────────

@router.callback_query(F.data.startswith("cm:"))
async def on_category_menu(callback: types.CallbackQuery, db=None):
    """Show category sub-menu: List, Channels, Latest item."""
    cat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    cats = await queries.get_all_categories(db, user_id)
    cat = next((c for c in cats if c["id"] == cat_id), None)
    if not cat:
        await callback.answer("Категория не найдена.")
        return

    emoji = cat.get("emoji", "📁")
    count = cat.get("item_count", 0)

    buttons = [
        [InlineKeyboardButton(text="📋 Список", callback_data=f"browse_cat:{cat_id}:0")],
        [InlineKeyboardButton(text="📨 Каналы", callback_data=f"cs:{cat_id}:0")],
        [InlineKeyboardButton(text="🆕 Последняя запись", callback_data=f"cl:{cat_id}")],
        [InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")],
    ]

    await callback.message.edit_text(
        f"{emoji} <b>{cat['name']}</b> ({count})",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cl:"))
async def on_category_latest(callback: types.CallbackQuery, db=None):
    """Jump to the latest item in a category."""
    cat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    items = await queries.get_items_page_with_nums(
        db, user_id, "category", context_id=cat_id, limit=1, offset=0,
    )
    if not items:
        await callback.answer("В этой категории нет записей.")
        return

    await _show_item_view(callback, "c", str(cat_id), items[0]["id"], db=db)


# ── Category Sources ──────────────────────────────────────

@router.callback_query(F.data.startswith("cs:"))
async def on_category_sources(callback: types.CallbackQuery, db=None):
    """Show sources/channels within a specific category."""
    parts = callback.data.split(":")
    cat_id = int(parts[1])
    user_id = callback.from_user.id

    sources = await queries.get_sources_by_category(db, user_id, cat_id)
    if not sources:
        await callback.answer("В этой категории нет пересланных записей из каналов.")
        return

    buttons = []
    for src in sources:
        name = src["source"]
        trunc = _truncate_source(name)
        buttons.append([InlineKeyboardButton(
            text=f"📨 {name} ({src['count']})",
            callback_data=f"src:{trunc}:0",
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К списку", callback_data=f"browse_cat:{cat_id}:0")])

    cats = await queries.get_all_categories(db, user_id)
    cat = next((c for c in cats if c["id"] == cat_id), None)
    cat_name = cat["name"] if cat else ""

    await callback.message.edit_text(
        f"📨 <b>Каналы в «{html.escape(cat_name)}»:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Hub: Tags ──────────────────────────────────────────────

@router.callback_query(F.data == "bm:tags")
async def on_hub_tags(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    tags = await queries.get_all_tags(db, user_id)
    if not tags:
        await callback.answer("Тегов пока нет.")
        return

    buttons = []
    row = []
    for t in tags:
        trunc = _truncate_tag(t["tag"])
        row.append(InlineKeyboardButton(
            text=f"#{t['tag']} ({t['count']})",
            callback_data=f"tag_items:{trunc}:0",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")])

    await callback.message.edit_text(
        "🏷 <b>Теги:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Hub: Map ───────────────────────────────────────────────

@router.callback_query(F.data == "bm:map")
async def on_hub_map(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    categories = await queries.get_category_tag_map(db, user_id)
    stats = await queries.get_stats(db, user_id)

    if not categories:
        await callback.answer("Карта знаний пуста.")
        return

    text = "🗺 <b>Карта знаний</b>\n\n"
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        count = cat.get("item_count", 0)
        tags = " ".join(f"#{t}" for t in cat.get("top_tags", []))
        text += f"{emoji} <b>{cat['name']}</b> ({count})\n"
        if tags:
            text += f"   {tags}\n"

    text += f"\n📊 Всего: {stats['items']} записей"

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} →",
            callback_data=f"browse_cat:{cat['id']}:0",
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Hub: Forgotten ─────────────────────────────────────────

@router.callback_query(F.data == "bm:forg")
async def on_hub_forgotten(callback: types.CallbackQuery, db=None):
    await _show_list(callback, "forgotten", "0", 0, db=db)


# ── Hub: Sources (channels) ──────────────────────────────

@router.callback_query(F.data.startswith("bm:sources"))
async def on_hub_sources(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id

    # Parse sort mode: bm:sources, bm:sources:c, bm:sources:d
    parts = callback.data.split(":")
    sort_mode = parts[2] if len(parts) > 2 else "c"

    if sort_mode == "d":
        sources = await queries.get_all_sources_by_date(db, user_id, ascending=False)
    else:
        sources = await queries.get_all_sources(db, user_id)

    if not sources:
        await callback.answer("Нет пересланных записей из каналов.")
        return

    # Sort toggle buttons
    sort_buttons = [
        InlineKeyboardButton(
            text=("✅ " if sort_mode == "c" else "") + "📊 По кол-ву",
            callback_data="bm:sources:c",
        ),
        InlineKeyboardButton(
            text=("✅ " if sort_mode == "d" else "") + "🕐 По дате",
            callback_data="bm:sources:d",
        ),
    ]

    buttons = [sort_buttons]
    for src in sources:
        name = src["source"]
        trunc = _truncate_source(name)
        buttons.append([InlineKeyboardButton(
            text=f"📨 {name} ({src['count']})",
            callback_data=f"src:{trunc}:0",
        )])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")])

    await callback.message.edit_text(
        "📨 <b>Все каналы:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("src:"))
async def on_browse_source(callback: types.CallbackQuery, db=None):
    # src:{source_name}:{offset}
    parts = callback.data.split(":")
    source_name = parts[1]
    offset = int(parts[2])
    # Source name may be truncated in callback — resolve full name from DB
    full_source = await queries.resolve_source_name(db, callback.from_user.id, source_name)
    await _show_list(callback, "source", full_source or source_name, offset, db=db)


# ── Hub: Collections ──────────────────────────────────────

@router.callback_query(F.data == "bm:colls")
async def on_hub_colls(callback: types.CallbackQuery, db=None):
    await _show_collections(callback, db=db)


@router.message(Command("collections"))
async def cmd_collections(message: types.Message, db=None):
    await _show_collections(message, db=db)


@router.callback_query(F.data.startswith("bc:"))
async def on_browse_collection(callback: types.CallbackQuery, db=None):
    # bc:{collection_id}:{offset}
    parts = callback.data.split(":")
    coll_id = parts[1]
    offset = int(parts[2])
    await _show_list(callback, "collection", coll_id, offset, db=db)


@router.callback_query(F.data == "bm:newcoll")
async def on_hub_newcoll(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    await set_state(db, f"new_collection_{user_id}", user_id, "new_collection", {})
    await callback.message.edit_text(
        "📁 <b>Новая коллекция</b>\n\nВведите название:",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Hub: New Category ─────────────────────────────────────

@router.callback_query(F.data == "bm:newcat")
async def on_hub_newcat(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    logger.info("bm:newcat callback: setting new_browse_cat state for user %d", user_id)
    await set_state(db, f"new_browse_cat_{user_id}", user_id, "new_browse_cat", {})
    await callback.message.edit_text(
        "📁 <b>Новая категория</b>\n\nВведите название:",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Clickable List View ───────────────────────────────────

@router.callback_query(F.data.startswith("browse_cat:"))
async def on_browse_category(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    cat_id = parts[1]
    offset = int(parts[2])
    sort_by = parts[3] if len(parts) > 3 else "d"
    await _show_list(callback, "category", cat_id, offset, db=db, sort_by=sort_by)


@router.callback_query(F.data.startswith("tag_items:"))
async def on_tag_items(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    tag = parts[1]
    offset = int(parts[2])
    await _show_list(callback, "tag", tag, offset, db=db)


@router.callback_query(F.data == "tags_back")
async def on_tags_back(callback: types.CallbackQuery, db=None):
    # Go back to tag cloud
    await on_hub_tags(callback, db=db)


# ── List pagination callback ──────────────────────────────

@router.callback_query(F.data.startswith("vl:"))
async def on_list_page(callback: types.CallbackQuery, db=None):
    # vl:{ctx_short}:{ctx_id}:{offset}:{sort_by}
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    offset = int(parts[3])
    sort_by = parts[4] if len(parts) > 4 else "d"
    context_type = _CTX_REV.get(ctx_short, "recent")
    await _show_list(callback, context_type, ctx_id, offset, db=db, sort_by=sort_by)


@router.callback_query(F.data.startswith("vd:"))
async def on_list_delete(callback: types.CallbackQuery, db=None):
    # vd:{ctx_short}:{ctx_id}:{item_id}:{offset}
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    item_id = int(parts[3])
    offset = int(parts[4])
    # Extract sort_by from vl: button on current keyboard
    ctx = _extract_list_context(callback)
    sort_by = ctx[3] if ctx else "d"
    context_type = _CTX_REV.get(ctx_short, "recent")
    await _show_list(callback, context_type, ctx_id, offset, db=db, deleting_item_id=item_id, sort_by=sort_by)


@router.callback_query(F.data.startswith("vy:"))
async def on_list_delete_confirm(callback: types.CallbackQuery, db=None):
    # vy:{ctx_short}:{ctx_id}:{item_id}:{offset}
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    item_id = int(parts[3])
    offset = int(parts[4])
    user_id = callback.from_user.id
    # Extract sort_by from vl: button on current keyboard
    ctx = _extract_list_context(callback)
    sort_by = ctx[3] if ctx else "d"

    if db is None:
        db = callback.bot.get("db")

    deleted = await queries.delete_item(db, user_id, item_id)
    if not deleted:
        await callback.answer("Запись не найдена.")
        return

    await callback.answer("🗑 Удалено")

    context_type = _CTX_REV.get(ctx_short, "recent")

    # Check if current page still has items
    items = await queries.get_items_page_with_nums(
        db, user_id, context_type,
        context_id=ctx_id if context_type in ("category", "tag", "collection", "source") else None,
        limit=PAGE_SIZE, offset=offset, sort_by=sort_by,
    )
    # If page is empty after delete, go back one page
    if not items and offset > 0:
        offset = max(0, offset - PAGE_SIZE)

    # Re-check after adjusted offset
    items = await queries.get_items_page_with_nums(
        db, user_id, context_type,
        context_id=ctx_id if context_type in ("category", "tag", "collection", "source") else None,
        limit=PAGE_SIZE, offset=offset, sort_by=sort_by,
    )
    if not items:
        await callback.message.edit_text(
            "📋 <b>Список пуст.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [_back_button_for_ctx(ctx_short, ctx_id)]
            ]),
            parse_mode="HTML",
        )
        return

    await _show_list(callback, context_type, ctx_id, offset, db=db, sort_by=sort_by)


@router.callback_query(F.data.startswith("vx:"))
async def on_list_delete_cancel(callback: types.CallbackQuery, db=None):
    # vx:{ctx_short}:{ctx_id}:{offset}
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    offset = int(parts[3])
    # Extract sort_by from vl: button on current keyboard
    ctx = _extract_list_context(callback)
    sort_by = ctx[3] if ctx else "d"
    context_type = _CTX_REV.get(ctx_short, "recent")
    await _show_list(callback, context_type, ctx_id, offset, db=db, sort_by=sort_by)


@router.callback_query(F.data == "noop")
async def on_noop(callback: types.CallbackQuery, db=None):
    await callback.answer()


# ── Single Item View ──────────────────────────────────────

@router.callback_query(F.data.startswith("vi:"))
async def on_view_item(callback: types.CallbackQuery, db=None):
    # vi:{ctx_short}:{ctx_id}:{item_id}
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    item_id = int(parts[3])
    await _show_item_view(callback, ctx_short, ctx_id, item_id, db=db)


@router.callback_query(F.data.startswith("vn:"))
async def on_nav_item(callback: types.CallbackQuery, db=None):
    # vn:{ctx_short}:{ctx_id}:{target_id}
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    target_id = int(parts[3])
    await _show_item_view(callback, ctx_short, ctx_id, target_id, db=db)


# ── Item Actions ──────────────────────────────────────────

@router.callback_query(F.data.startswith("va:pin:"))
async def on_action_pin(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await callback.answer("Запись не найдена.")
        return

    if item.get("is_pinned"):
        await queries.unpin_item(db, user_id, item_id)
        await callback.answer("📌 Откреплено")
    else:
        await queries.pin_item(db, user_id, item_id)
        await callback.answer("📌 Закреплено")

    # Refresh — find context from the message buttons
    ctx = _extract_list_context(callback)
    if ctx:
        ctx_short, ctx_id, _, sort_by = ctx
        await _show_item_view(callback, ctx_short, ctx_id, item_id, db=db, sort_by=sort_by)
        return


@router.callback_query(F.data.startswith("va:del:"))
async def on_action_delete(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    ctx = _extract_list_context(callback)

    buttons = [
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"va:dyes:{item_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"va:dno:{item_id}"),
        ]
    ]
    if ctx:
        ctx_short, ctx_id, offset, sort_by = ctx
        buttons.append([InlineKeyboardButton(
            text="🔙 К списку",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset}:{sort_by}",
        )])

    await callback.message.edit_text(
        f"🗑 Удалить запись #{item_id}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("va:dyes:"))
async def on_action_delete_confirm(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    if db is None:
        db = callback.bot.get("db")

    ctx = _extract_list_context(callback)

    deleted = await queries.delete_item(db, user_id, item_id)
    if not deleted:
        await callback.answer("Запись не найдена.")
        return

    await callback.answer("🗑 Удалено")

    if ctx:
        ctx_short, ctx_id, offset, sort_by = ctx
        context_type = _CTX_REV.get(ctx_short, "recent")

        # Check if current page still has items
        items = await queries.get_items_page_with_nums(
            db, user_id, context_type,
            context_id=ctx_id if context_type in ("category", "tag", "collection", "source") else None,
            limit=PAGE_SIZE, offset=offset, sort_by=sort_by,
        )
        if not items and offset > 0:
            offset = max(0, offset - PAGE_SIZE)

        items = await queries.get_items_page_with_nums(
            db, user_id, context_type,
            context_id=ctx_id if context_type in ("category", "tag", "collection", "source") else None,
            limit=PAGE_SIZE, offset=offset, sort_by=sort_by,
        )
        if not items:
            await callback.message.edit_text(
                "📋 <b>Список пуст.</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [_back_button_for_ctx(ctx_short, ctx_id)]
                ]),
                parse_mode="HTML",
            )
            return

        await _show_list(callback, context_type, ctx_id, offset, db=db, sort_by=sort_by)
    else:
        await callback.message.edit_text(
            "🗑 Запись удалена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")]
            ]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("va:dno:"))
async def on_action_delete_cancel(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    await callback.answer("Отменено")

    ctx = _extract_list_context(callback)
    if ctx:
        ctx_short, ctx_id, _, sort_by = ctx
        await _show_item_view(callback, ctx_short, ctx_id, item_id, db=db, sort_by=sort_by)
    else:
        await callback.message.edit_text(
            "↩️ Удаление отменено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")]
            ]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("va:move:"))
async def on_action_move(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await callback.answer("Нет категорий для перемещения.")
        return

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']}",
            callback_data=f"va:mc:{item_id}:{cat['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bm:cats")])

    await callback.message.edit_text(
        f"📂 Переместить запись #{item_id} в категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("va:mc:"))
async def on_action_move_confirm(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    item_id = int(parts[2])
    cat_id = int(parts[3])
    user_id = callback.from_user.id

    moved = await queries.update_item_category(db, user_id, item_id, cat_id)
    if moved:
        await callback.answer("📂 Перемещено")
        # Show item in new context
        await _show_item_view(callback, "c", str(cat_id), item_id, db=db)
    else:
        await callback.answer("Ошибка перемещения.")


@router.callback_query(F.data.startswith("va:tags:"))
async def on_action_tags(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await callback.answer("Запись не найдена.")
        return

    tags = item.get("tags", [])
    tags_str = " ".join(f"#{t}" for t in tags) if tags else "нет тегов"

    await set_state(db, f"edit_tags_{user_id}", user_id, "edit_tags", {"item_id": item_id})
    await callback.message.edit_text(
        f"🏷 <b>Текущие теги:</b> {tags_str}\n\n"
        f"Введите новые теги через пробел (без #):",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("va:note:"))
async def on_action_note(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await callback.answer("Запись не найдена.")
        return

    current = item.get("user_note") or "нет заметки"

    await set_state(db, f"edit_note_{user_id}", user_id, "edit_note", {"item_id": item_id})
    await callback.message.edit_text(
        f"💭 <b>Текущая заметка:</b> {html.escape(current)}\n\n"
        f"✏️ Введите заметку:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("va:rel:"))
async def on_action_related(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    item_id = int(callback.data.split(":")[2])

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await callback.answer("Запись не найдена.")
        return

    related = await find_related_items(
        db, item_id, user_id,
        category_id=item.get("category_id"),
        tags=item.get("tags", []),
        source=item.get("source"),
    )

    if not related:
        await callback.answer("Похожих записей не найдено", show_alert=False)
        return

    # Preserve original browsing context for navigation
    ctx = _extract_list_context(callback)
    ctx_short, ctx_id = (ctx[0], ctx[1]) if ctx else ("r", "0")
    # sort_by from ctx[3] if available, for back navigation

    lines = ["🔗 <b>Похожие записи:</b>\n"]
    buttons = []
    for r in related:
        title = _format_item_short(r)
        lines.append(f"• <b>#{r['id']}</b> {html.escape(title)}")
        buttons.append([InlineKeyboardButton(
            text=f"#{r['id']} {title}",
            callback_data=f"vi:{ctx_short}:{ctx_id}:{r['id']}",
        )])

    buttons.append([InlineKeyboardButton(
        text="🔙 К записи",
        callback_data=f"vi:{ctx_short}:{ctx_id}:{item_id}",
    )])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("va:coll:"))
async def on_action_add_to_collection(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    item_id = int(callback.data.split(":")[2])

    colls = await queries.get_collections(db, user_id)

    buttons = []
    for coll in colls:
        emoji = coll.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {coll['name']}",
            callback_data=f"va:ac:{item_id}:{coll['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="➕ Новая", callback_data=f"va:nc:{item_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 К записи", callback_data=f"vi:r:0:{item_id}")])

    await callback.message.edit_text(
        "📁 <b>Добавить в коллекцию:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("va:ac:"))
async def on_action_add_to_coll_confirm(callback: types.CallbackQuery, db=None):
    # va:ac:{item_id}:{coll_id}
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    item_id = int(parts[2])
    coll_id = int(parts[3])

    added = await queries.add_to_collection(db, user_id, coll_id, item_id)
    if added:
        await callback.answer("✅ Добавлено в коллекцию")
    else:
        await callback.answer("Уже в коллекции или ошибка")

    # Return to item view
    await _show_item_view(callback, "r", "0", item_id, db=db)


@router.callback_query(F.data.startswith("va:nc:"))
async def on_action_new_collection_for_item(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    item_id = int(callback.data.split(":")[2])

    await set_state(db, f"new_collection_{user_id}", user_id, "new_collection", {"item_id": item_id})
    await callback.message.edit_text(
        "📁 <b>Новая коллекция</b>\n\nВведите название:",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Legacy /tags command ──────────────────────────────────

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
        trunc = _truncate_tag(t["tag"])
        row.append(InlineKeyboardButton(
            text=f"#{t['tag']} ({t['count']})",
            callback_data=f"tag_items:{trunc}:0",
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


# ── /search ───────────────────────────────────────────────

@router.message(Command("search"))
async def cmd_search(message: types.Message, db=None, query_override: str | None = None):
    user_id = message.from_user.id
    query = query_override or message.text.replace("/search", "", 1).strip()
    if not query:
        await message.reply("Использование: /search &lt;запрос&gt;")
        return

    wait_msg = await message.reply("⏳ Ищу...")

    # Try AI-powered search first
    parsed = await parse_search_query(query)
    items = None
    search_info = ""

    if parsed and parsed.get("keywords"):
        # Show what AI understood
        info_parts = []
        if parsed["keywords"]:
            info_parts.append(f"Ключевые слова: {html.escape(', '.join(parsed['keywords']))}")
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
        await wait_msg.edit_text(f"🔍 По запросу «{query}» ничего не найдено.")
        return

    # Build clickable search results
    text = f"{search_info}🔍 <b>Результаты ({len(items)}):</b>"
    buttons = []
    for i, item in enumerate(items, 1):
        title = _format_item_short(item)
        buttons.append([InlineKeyboardButton(
            text=f"{i}. {title}",
            callback_data=f"vi:r:0:{item['id']}",
        )])

    await wait_msg.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.message(Command("ask"))
async def cmd_ask(message: types.Message, db=None):
    await message.reply("⚠️ Команда /ask временно отключена. Используйте /search для поиска.")


# ── /recent (clickable) ──────────────────────────────────

@router.message(Command("recent"))
async def cmd_recent(message: types.Message, db=None):
    user_id = message.from_user.id
    items = await queries.get_items_page_with_nums(db, user_id, "recent", limit=PAGE_SIZE, offset=0)
    if not items:
        await message.reply("Пока нет сохранённых записей.")
        return

    all_items = await queries.get_items_page_with_nums(db, user_id, "recent", limit=10000, offset=0)
    total = len(all_items)

    buttons = _clickable_list_buttons(items, "r", "0", 0, total)
    buttons.append([_back_button_for_ctx("r")])

    await message.reply(
        f"🕐 <b>Последние записи</b> ({total})",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


# ── /pinned (clickable) ──────────────────────────────────

@router.message(Command("pinned"))
async def cmd_pinned(message: types.Message, db=None):
    user_id = message.from_user.id
    items = await queries.get_items_page_with_nums(db, user_id, "pinned", limit=PAGE_SIZE, offset=0)
    if not items:
        await message.reply("📌 Нет закреплённых записей. Используйте /pin &lt;id&gt; чтобы закрепить.")
        return

    all_items = await queries.get_items_page_with_nums(db, user_id, "pinned", limit=10000, offset=0)
    total = len(all_items)

    buttons = _clickable_list_buttons(items, "p", "0", 0, total)
    buttons.append([_back_button_for_ctx("p")])

    await message.reply(
        f"📌 <b>Закреплённые записи</b> ({total})",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.message(Command("pin"))
async def cmd_pin(message: types.Message, db=None):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /pin &lt;id&gt;")
        return
    try:
        item_id = int(parts[1])
    except ValueError:
        await message.reply("ID должен быть числом.")
        return

    if await queries.pin_item(db, user_id, item_id):
        await message.reply(f"📌 Запись #{item_id} закреплена.")
    else:
        await message.reply(f"Запись #{item_id} не найдена.")


@router.message(Command("unpin"))
async def cmd_unpin(message: types.Message, db=None):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /unpin &lt;id&gt;")
        return
    try:
        item_id = int(parts[1])
    except ValueError:
        await message.reply("ID должен быть числом.")
        return

    if await queries.unpin_item(db, user_id, item_id):
        await message.reply(f"📌 Запись #{item_id} откреплена.")
    else:
        await message.reply(f"Запись #{item_id} не найдена.")


# ── /map ──────────────────────────────────────────────────

@router.message(Command("map"))
async def cmd_map(message: types.Message, db=None):
    user_id = message.from_user.id
    categories = await queries.get_category_tag_map(db, user_id)
    stats = await queries.get_stats(db, user_id)

    if not categories:
        await message.reply("🗺 Карта знаний пуста. Сохрани что-нибудь!")
        return

    text = "🗺 <b>Карта знаний</b>\n\n"
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        count = cat.get("item_count", 0)
        tags = " ".join(f"#{t}" for t in cat.get("top_tags", []))
        text += f"{emoji} <b>{cat['name']}</b> ({count})\n"
        if tags:
            text += f"   {tags}\n"

    text += f"\n📊 Всего: {stats['items']} записей, {stats['categories']} категорий, {stats['tags']} тегов"

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} →",
            callback_data=f"browse_cat:{cat['id']}:0",
        )])

    await message.reply(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


# ── /forgotten ────────────────────────────────────────────

@router.message(Command("forgotten"))
async def cmd_forgotten(message: types.Message, db=None):
    user_id = message.from_user.id
    items = await queries.get_items_page_with_nums(db, user_id, "forgotten", limit=PAGE_SIZE, offset=0)

    if not items:
        await message.reply("✨ Нет забытых записей! Все записи свежие или закреплены.")
        return

    all_items = await queries.get_items_page_with_nums(db, user_id, "forgotten", limit=10000, offset=0)
    total = len(all_items)

    buttons = _clickable_list_buttons(items, "f", "0", 0, total)
    buttons.append([_back_button_for_ctx("f")])

    await message.reply(
        f"🕸 <b>Забытые записи</b> ({total})",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
