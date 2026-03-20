"""Browse and search handlers."""

from __future__ import annotations

import html
import logging
import math

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.db.state_store import set_state
from savebot.services.ai_search import parse_search_query
from savebot.services.connections import find_related_items

router = Router()
logger = logging.getLogger(__name__)
PAGE_SIZE = 5

# Context type short codes for callback data
_CTX_MAP = {"category": "c", "tag": "t", "recent": "r", "pinned": "p", "forgotten": "f", "collection": "o", "source": "s"}
_CTX_REV = {v: k for k, v in _CTX_MAP.items()}

# Context titles
_CTX_TITLES = {
    "category": "📂 Категория",
    "tag": "🏷 Тег",
    "recent": "🕐 Последние записи",
    "pinned": "📌 Закреплённые",
    "forgotten": "🕸 Забытые записи",
    "collection": "📁 Коллекция",
    "source": "📨 Каналы",
}


# ── Sort ──────────────────────────────────────────────────

SORT_LABELS = {
    "d": "\U0001f554 \u041d\u043e\u0432\u044b\u0435",
    "p": "\U0001f4cc \u0417\u0430\u043a\u0440\u0435\u043f",
    "a": "\U0001f524 A-Z",
    "s": "\U0001f4e8 \u041a\u0430\u043d\u0430\u043b",
}


def _sort_buttons(cat_id: int, active_sort: str = "d") -> list[InlineKeyboardButton]:
    """Build sort option buttons for category view."""
    row = []
    for key, label in SORT_LABELS.items():
        mark = "\u2705 " if key == active_sort else ""
        row.append(InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"browse_cat:{cat_id}:0:{key}",
        ))
    return row


def _recent_sort_buttons(active_sort: str = "d") -> list[InlineKeyboardButton]:
    """Build date direction toggle for Recent view."""
    return [
        InlineKeyboardButton(
            text=("✅ " if active_sort == "d" else "") + "🕐 Новые",
            callback_data="vl:r:0:0:d",
        ),
        InlineKeyboardButton(
            text=("✅ " if active_sort == "o" else "") + "📅 Старые",
            callback_data="vl:r:0:0:o",
        ),
    ]


# ── Helpers ────────────────────────────────────────────────

def _truncate_tag(tag: str, max_len: int = 20) -> str:
    """Truncate tag for use in callback data."""
    return tag[:max_len]


def _format_item_short(item: dict) -> str:
    """Short one-line format for button text (max ~40 chars)."""
    if item.get("ai_summary"):
        title = item["ai_summary"]
    elif item.get("content_text"):
        title = item["content_text"]
    else:
        title = "(без текста)"
    if len(title) > 38:
        title = title[:35] + "..."
    return title


def _format_item_full(item: dict, position: int | None = None, total: int | None = None) -> str:
    """Full format for single item view."""
    parts = []

    # Header with position
    header = f"<b>#{item['id']}</b>"
    if position and total:
        header = f"📝 {position} / {total}  |  {header}"
    if item.get("category_name"):
        emoji = item.get("category_emoji", "📁")
        header += f"  |  {emoji} {item['category_name']}"
    parts.append(header)

    # Content
    if item.get("ai_summary"):
        parts.append(f"\n{item['ai_summary']}")
    if item.get("content_text"):
        text = item["content_text"]
        if len(text) > 500:
            text = text[:500] + "..."
        parts.append(f"\n{html.escape(text)}")

    # Tags
    tags = item.get("tags", [])
    if tags:
        parts.append("\n" + " ".join(f"#{t}" for t in tags))

    # Personal note
    if item.get("user_note"):
        parts.append(f"\n💭 {html.escape(item['user_note'])}")

    # Source (for forwards)
    if item.get("source"):
        parts.append(f"\n📨 Переслано из: {html.escape(item['source'])}")

    # URL
    if item.get("url"):
        parts.append(f"\n🔗 {item['url']}")

    return "\n".join(parts)


def _format_item(item: dict) -> str:
    """Legacy short format for search results etc."""
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


def _clickable_list_buttons(
    items: list[dict],
    ctx_short: str,
    ctx_id: str | int,
    offset: int,
    total: int,
    deleting_item_id: int | None = None,
    sort_by: str = "d",
) -> list[list[InlineKeyboardButton]]:
    """Build clickable item buttons + pagination for a list view."""
    buttons = []
    for item in items:
        if deleting_item_id and item["id"] == deleting_item_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"Удалить #{item['id']}?", callback_data="noop",
                ),
                InlineKeyboardButton(
                    text="✅", callback_data=f"vy:{ctx_short}:{ctx_id}:{item['id']}:{offset}",
                ),
                InlineKeyboardButton(
                    text="❌", callback_data=f"vx:{ctx_short}:{ctx_id}:{offset}",
                ),
            ])
        else:
            num = item.get("display_num", item["id"])
            title = _format_item_short(item)
            cb = f"vi:{ctx_short}:{ctx_id}:{item['id']}"
            buttons.append([
                InlineKeyboardButton(text=f"{num}. {title}", callback_data=cb),
                InlineKeyboardButton(
                    text="🗑", callback_data=f"vd:{ctx_short}:{ctx_id}:{item['id']}:{offset}",
                ),
            ])

    # Pagination row
    page = offset // PAGE_SIZE + 1
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset - PAGE_SIZE}:{sort_by}",
        ))
    nav.append(InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="noop"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset + PAGE_SIZE}:{sort_by}",
        ))
    if nav:
        buttons.append(nav)

    return buttons


def _back_button_for_ctx(ctx_short: str, ctx_id: str | int = "0") -> InlineKeyboardButton:
    """Return the appropriate back button for a given context."""
    if ctx_short == "c":
        return InlineKeyboardButton(text="🔙 К категории", callback_data=f"cm:{ctx_id}")
    elif ctx_short == "t":
        return InlineKeyboardButton(text="🔙 К тегам", callback_data="tags_back")
    elif ctx_short == "o":
        return InlineKeyboardButton(text="🔙 К коллекциям", callback_data="bm:colls")
    elif ctx_short == "s":
        return InlineKeyboardButton(text="🔙 К каналам", callback_data="bm:sources")
    else:
        return InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")


# ── /browse — Categories (main screen) ─────────────────────

def _more_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Теги", callback_data="bm:tags")],
        [InlineKeyboardButton(text="📁 Коллекции", callback_data="bm:colls")],
        [InlineKeyboardButton(text="🗺 Карта знаний", callback_data="bm:map")],
        [InlineKeyboardButton(text="➕ Новая категория", callback_data="bm:newcat")],
        [InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")],
    ])


def _categories_markup(categories: list[dict]) -> InlineKeyboardMarkup:
    """Build category list buttons with footer."""
    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"cm:{cat['id']}",
        )])
    buttons.append([
        InlineKeyboardButton(text="📨 Все каналы", callback_data="bm:sources"),
        InlineKeyboardButton(text="📋 Ещё", callback_data="bm:hub"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _show_categories_msg(message: types.Message, db=None):
    """Show category list for commands/keyboard (sends new message)."""
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await message.reply(
            "📂 <b>Категорий пока нет.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Ещё", callback_data="bm:hub")]
            ]),
            parse_mode="HTML",
        )
        return
    await message.reply(
        "📂 <b>Категории:</b>",
        reply_markup=_categories_markup(categories),
        parse_mode="HTML",
    )


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
            "📂 <b>Категорий пока нет.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Ещё", callback_data="bm:hub")]
            ]),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📂 <b>Категории:</b>",
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
    buttons.append([InlineKeyboardButton(text="🔙 К категории", callback_data=f"cm:{cat_id}")])

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

def _truncate_source(source: str, max_len: int = 40) -> str:
    """Truncate source name for use in callback data."""
    return source[:max_len]


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
    await _show_list(callback, "source", source_name, offset, db=db)


# ── Hub: Collections ──────────────────────────────────────

async def _show_collections(callback_or_msg, db=None):
    """Show collections list. Works with both callback and message."""
    if isinstance(callback_or_msg, types.CallbackQuery):
        user_id = callback_or_msg.from_user.id
    else:
        user_id = callback_or_msg.from_user.id

    colls = await queries.get_collections(db, user_id)

    buttons = []
    for coll in colls:
        emoji = coll.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {coll['name']} ({coll['item_count']})",
            callback_data=f"bc:{coll['id']}:0",
        )])
    buttons.append([InlineKeyboardButton(text="➕ Новая коллекция", callback_data="bm:newcoll")])
    buttons.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")])

    text = "📁 <b>Коллекции:</b>" if colls else "📁 <b>Коллекций пока нет.</b>"
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(callback_or_msg, types.CallbackQuery):
        await callback_or_msg.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback_or_msg.answer()
    else:
        await callback_or_msg.reply(text, reply_markup=markup, parse_mode="HTML")


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

async def _show_list(callback: types.CallbackQuery, context_type: str, ctx_id: str | int, offset: int, db=None, deleting_item_id: int | None = None, sort_by: str = "d"):
    """Show a clickable item list for any context."""
    if db is None:
        db = callback.bot.get("db")
    user_id = callback.from_user.id
    ctx_short = _CTX_MAP.get(context_type, "r")

    items = await queries.get_items_page_with_nums(
        db, user_id, context_type, context_id=ctx_id if context_type in ("category", "tag", "collection", "source") else None,
        limit=PAGE_SIZE, offset=offset, sort_by=sort_by,
    )

    if not items:
        await callback.answer("Записей нет.")
        return

    # Get total count
    if context_type == "category":
        total = await queries.count_items_in_category(db, user_id, int(ctx_id))
    elif context_type == "tag":
        total = await queries.count_items_by_tag(db, user_id, str(ctx_id))
    elif context_type == "collection":
        total = await queries.count_collection_items(db, user_id, int(ctx_id))
    elif context_type == "source":
        total = await queries.count_items_by_source(db, user_id, str(ctx_id))
    else:
        # Use a general approach — get_items_page_with_nums with high limit to count
        # For simplicity, estimate from display_num of last item
        if items:
            # Re-query without limit for count
            all_items = await queries.get_items_page_with_nums(
                db, user_id, context_type, context_id=None, limit=10000, offset=0,
            )
            total = len(all_items)
        else:
            total = 0

    title = _CTX_TITLES.get(context_type, "📋 Записи")
    if context_type == "category":
        # Get category name
        cats = await queries.get_all_categories(db, user_id)
        cat_name = next((c["name"] for c in cats if c["id"] == int(ctx_id)), "")
        cat_emoji = next((c.get("emoji", "📁") for c in cats if c["id"] == int(ctx_id)), "📁")
        title = f"{cat_emoji} <b>{cat_name}</b> ({total})"
    elif context_type == "tag":
        title = f"🏷 <b>#{ctx_id}</b> ({total})"
    elif context_type == "collection":
        colls = await queries.get_collections(db, user_id)
        coll_name = next((c["name"] for c in colls if c["id"] == int(ctx_id)), "")
        coll_emoji = next((c.get("emoji", "📁") for c in colls if c["id"] == int(ctx_id)), "📁")
        title = f"{coll_emoji} <b>{coll_name}</b> ({total})"
    elif context_type == "source":
        title = f"📨 <b>{html.escape(str(ctx_id))}</b> ({total})"
    else:
        title = f"{title} ({total})"

    buttons = _clickable_list_buttons(items, ctx_short, ctx_id, offset, total, deleting_item_id=deleting_item_id, sort_by=sort_by)
    if context_type == "category":
        buttons.insert(0, _sort_buttons(int(ctx_id), sort_by))
    elif context_type == "recent":
        buttons.insert(0, _recent_sort_buttons(sort_by))
    buttons.append([_back_button_for_ctx(ctx_short, ctx_id)])

    await callback.message.edit_text(
        title,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


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

async def _show_item_view(callback: types.CallbackQuery, ctx_short: str, ctx_id: str | int, item_id: int, db=None, sort_by: str = "d"):
    """Show full single item view with navigation and actions."""
    if db is None:
        db = callback.bot.get("db")
    user_id = callback.from_user.id
    context_type = _CTX_REV.get(ctx_short, "recent")

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await callback.answer("Запись не найдена.")
        return

    # Get category info for display
    if item.get("category_id"):
        cats = await queries.get_all_categories(db, user_id)
        cat = next((c for c in cats if c["id"] == item["category_id"]), None)
        if cat:
            item["category_name"] = cat["name"]
            item["category_emoji"] = cat.get("emoji", "📁")

    # Get adjacent items for navigation
    nav = await queries.get_adjacent_item_ids(
        db, user_id, item_id, context_type,
        context_id=ctx_id if context_type in ("category", "tag", "collection", "source") else None,
        sort_by=sort_by,
    )

    position = nav["position"] if nav else None
    total = nav["total"] if nav else None

    text = _format_item_full(item, position, total)

    # Build buttons
    buttons = []

    # Navigation row: prev / position / next
    nav_row = []
    if nav and nav.get("prev_id"):
        nav_row.append(InlineKeyboardButton(
            text="⬅️ Пред",
            callback_data=f"vn:{ctx_short}:{ctx_id}:{nav['prev_id']}",
        ))
    if position and total:
        nav_row.append(InlineKeyboardButton(text=f"{position}/{total}", callback_data="noop"))
    if nav and nav.get("next_id"):
        nav_row.append(InlineKeyboardButton(
            text="След ➡️",
            callback_data=f"vn:{ctx_short}:{ctx_id}:{nav['next_id']}",
        ))
    if nav_row:
        buttons.append(nav_row)

    # Action row 1: pin, move, delete
    actions1 = []
    if item.get("is_pinned"):
        actions1.append(InlineKeyboardButton(text="📌 Открепить", callback_data=f"va:pin:{item_id}"))
    else:
        actions1.append(InlineKeyboardButton(text="📌 Закрепить", callback_data=f"va:pin:{item_id}"))
    actions1.append(InlineKeyboardButton(text="📂 Переместить", callback_data=f"va:move:{item_id}"))
    actions1.append(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"va:del:{item_id}"))
    buttons.append(actions1)

    # Forward original post button
    if item.get("forward_url"):
        buttons.append([InlineKeyboardButton(text="📨 Оригинал", url=item["forward_url"])])

    # Action row 2: tags, note, related, collection
    actions2 = []
    actions2.append(InlineKeyboardButton(text="🏷 Теги", callback_data=f"va:tags:{item_id}"))
    actions2.append(InlineKeyboardButton(text="✏️ Заметка", callback_data=f"va:note:{item_id}"))
    actions2.append(InlineKeyboardButton(text="🔗 Похожие", callback_data=f"va:rel:{item_id}"))
    actions2.append(InlineKeyboardButton(text="📁+", callback_data=f"va:coll:{item_id}"))
    buttons.append(actions2)

    # Back to list row
    back_offset = max(0, ((position - 1) // PAGE_SIZE) * PAGE_SIZE) if position else 0
    buttons.append([InlineKeyboardButton(
        text="🔙 К списку",
        callback_data=f"vl:{ctx_short}:{ctx_id}:{back_offset}:{sort_by}",
    )])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


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


def _extract_list_context(callback: types.CallbackQuery) -> tuple[str, str, int, str] | None:
    """Extract (ctx_short, ctx_id, offset, sort_by) from the vl: back button in current keyboard."""
    kb = callback.message.reply_markup
    if kb and kb.inline_keyboard:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("vl:"):
                    parts = btn.callback_data.split(":")
                    sort_by = parts[4] if len(parts) > 4 else "d"
                    return parts[1], parts[2], int(parts[3]), sort_by
    return None


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
