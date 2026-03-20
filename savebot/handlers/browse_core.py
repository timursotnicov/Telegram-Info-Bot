"""Shared helpers and core display functions for browse handlers."""
from __future__ import annotations

import html
import logging
import math

from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries

logger = logging.getLogger(__name__)

PAGE_SIZE = 5

# Context type short codes for callback data
_CTX_MAP = {"category": "c", "tag": "t", "recent": "r", "pinned": "p", "forgotten": "f", "collection": "o", "source": "s"}
_CTX_REV = {v: k for k, v in _CTX_MAP.items()}

# Context titles
_CTX_TITLES = {
    "category": "\U0001f4c2 \u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f",
    "tag": "\U0001f3f7 \u0422\u0435\u0433",
    "recent": "\U0001f550 \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u0437\u0430\u043f\u0438\u0441\u0438",
    "pinned": "\U0001f4cc \u0417\u0430\u043a\u0440\u0435\u043f\u043b\u0451\u043d\u043d\u044b\u0435",
    "forgotten": "\U0001f578 \u0417\u0430\u0431\u044b\u0442\u044b\u0435 \u0437\u0430\u043f\u0438\u0441\u0438",
    "collection": "\U0001f4c1 \u041a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u044f",
    "source": "\U0001f4e8 \u041a\u0430\u043d\u0430\u043b\u044b",
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
            text=("\u2705 " if active_sort == "d" else "") + "\U0001f550 \u041d\u043e\u0432\u044b\u0435",
            callback_data="vl:r:0:0:d",
        ),
        InlineKeyboardButton(
            text=("\u2705 " if active_sort == "o" else "") + "\U0001f4c5 \u0421\u0442\u0430\u0440\u044b\u0435",
            callback_data="vl:r:0:0:o",
        ),
    ]


# ── Helpers ────────────────────────────────────────────────

def _truncate_tag(tag: str, max_len: int = 20) -> str:
    """Truncate tag for use in callback data."""
    return tag[:max_len]


def _truncate_source(source: str, max_bytes: int = 56) -> str:
    """Truncate source name for callback data (64 byte limit).

    Budget: 64 - len("src:") - len(":0") = 58 bytes, minus 2 margin = 56.
    """
    encoded = source.encode("utf-8")
    if len(encoded) <= max_bytes:
        return source
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated


def _format_item_short(item: dict) -> str:
    """Short one-line format for button text (max ~40 chars)."""
    if item.get("ai_summary"):
        title = item["ai_summary"]
    elif item.get("content_text"):
        title = item["content_text"]
    else:
        title = "(\u0431\u0435\u0437 \u0442\u0435\u043a\u0441\u0442\u0430)"
    if len(title) > 38:
        title = title[:35] + "..."
    return title


def _format_item_full(item: dict, position: int | None = None, total: int | None = None) -> str:
    """Full format for single item view."""
    parts = []

    # Header with position
    header = f"<b>#{item['id']}</b>"
    if position and total:
        header = f"\U0001f4dd {position} / {total}  |  {header}"
    if item.get("category_name"):
        emoji = item.get("category_emoji", "\U0001f4c1")
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
        parts.append(f"\n\U0001f4ad {html.escape(item['user_note'])}")

    # Source (for forwards)
    if item.get("source"):
        parts.append(f"\n\U0001f4e8 \u041f\u0435\u0440\u0435\u0441\u043b\u0430\u043d\u043e \u0438\u0437: {html.escape(item['source'])}")

    # URL
    if item.get("url"):
        parts.append(f"\n\U0001f517 {item['url']}")

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
        text += f"\n\U0001f517 {item['url']}"
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
                    text=f"\u0423\u0434\u0430\u043b\u0438\u0442\u044c #{item['id']}?", callback_data="noop",
                ),
                InlineKeyboardButton(
                    text="\u2705", callback_data=f"vy:{ctx_short}:{ctx_id}:{item['id']}:{offset}",
                ),
                InlineKeyboardButton(
                    text="\u274c", callback_data=f"vx:{ctx_short}:{ctx_id}:{offset}",
                ),
            ])
        else:
            num = item.get("display_num", item["id"])
            title = _format_item_short(item)
            cb = f"vi:{ctx_short}:{ctx_id}:{item['id']}"
            buttons.append([
                InlineKeyboardButton(text=f"{num}. {title}", callback_data=cb),
                InlineKeyboardButton(
                    text="\U0001f5d1", callback_data=f"vd:{ctx_short}:{ctx_id}:{item['id']}:{offset}",
                ),
            ])

    # Pagination row
    page = offset // PAGE_SIZE + 1
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="\u2b05\ufe0f",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset - PAGE_SIZE}:{sort_by}",
        ))
    nav.append(InlineKeyboardButton(text=f"\u0421\u0442\u0440. {page}/{total_pages}", callback_data="noop"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="\u27a1\ufe0f",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset + PAGE_SIZE}:{sort_by}",
        ))
    if nav:
        buttons.append(nav)

    return buttons


def _back_button_for_ctx(ctx_short: str, ctx_id: str | int = "0") -> InlineKeyboardButton:
    """Return the appropriate back button for a given context."""
    if ctx_short == "c":
        return InlineKeyboardButton(text="\U0001f519 \u041a \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438", callback_data=f"cm:{ctx_id}")
    elif ctx_short == "t":
        return InlineKeyboardButton(text="\U0001f519 \u041a \u0442\u0435\u0433\u0430\u043c", callback_data="tags_back")
    elif ctx_short == "o":
        return InlineKeyboardButton(text="\U0001f519 \u041a \u043a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u044f\u043c", callback_data="bm:colls")
    elif ctx_short == "s":
        return InlineKeyboardButton(text="\U0001f519 \u041a \u043a\u0430\u043d\u0430\u043b\u0430\u043c", callback_data="bm:sources")
    else:
        return InlineKeyboardButton(text="\U0001f519 \u041a \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f\u043c", callback_data="bm:cats")


def _more_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f3f7 \u0422\u0435\u0433\u0438", callback_data="bm:tags")],
        [InlineKeyboardButton(text="\U0001f4c1 \u041a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u0438", callback_data="bm:colls")],
        [InlineKeyboardButton(text="\U0001f5fa \u041a\u0430\u0440\u0442\u0430 \u0437\u043d\u0430\u043d\u0438\u0439", callback_data="bm:map")],
        [InlineKeyboardButton(text="\u2795 \u041d\u043e\u0432\u0430\u044f \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f", callback_data="bm:newcat")],
        [InlineKeyboardButton(text="\U0001f519 \u041a \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f\u043c", callback_data="bm:cats")],
    ])


def _categories_markup(categories: list[dict]) -> InlineKeyboardMarkup:
    """Build category list buttons with footer."""
    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "\U0001f4c1")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"cm:{cat['id']}",
        )])
    buttons.append([
        InlineKeyboardButton(text="\U0001f4e8 \u0412\u0441\u0435 \u043a\u0430\u043d\u0430\u043b\u044b", callback_data="bm:sources"),
        InlineKeyboardButton(text="\U0001f4cb \u0415\u0449\u0451", callback_data="bm:hub"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


# ── Core display functions ────────────────────────────────

async def _show_categories_msg(message: types.Message, db=None):
    """Show category list for commands/keyboard (sends new message)."""
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await message.reply(
            "\U0001f4c2 <b>\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f4cb \u0415\u0449\u0451", callback_data="bm:hub")]
            ]),
            parse_mode="HTML",
        )
        return
    await message.reply(
        "\U0001f4c2 <b>\u041a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438:</b>",
        reply_markup=_categories_markup(categories),
        parse_mode="HTML",
    )


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
        await callback.answer("\u0417\u0430\u043f\u0438\u0441\u0435\u0439 \u043d\u0435\u0442.")
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
        total = await queries.count_items_in_context(db, user_id, context_type)

    title = _CTX_TITLES.get(context_type, "\U0001f4cb \u0417\u0430\u043f\u0438\u0441\u0438")
    if context_type == "category":
        # Get category name
        cats = await queries.get_all_categories(db, user_id)
        cat_name = next((c["name"] for c in cats if c["id"] == int(ctx_id)), "")
        cat_emoji = next((c.get("emoji", "\U0001f4c1") for c in cats if c["id"] == int(ctx_id)), "\U0001f4c1")
        title = f"{cat_emoji} <b>{cat_name}</b> ({total})"
    elif context_type == "tag":
        title = f"\U0001f3f7 <b>#{ctx_id}</b> ({total})"
    elif context_type == "collection":
        colls = await queries.get_collections(db, user_id)
        coll_name = next((c["name"] for c in colls if c["id"] == int(ctx_id)), "")
        coll_emoji = next((c.get("emoji", "\U0001f4c1") for c in colls if c["id"] == int(ctx_id)), "\U0001f4c1")
        title = f"{coll_emoji} <b>{coll_name}</b> ({total})"
    elif context_type == "source":
        title = f"\U0001f4e8 <b>{html.escape(str(ctx_id))}</b> ({total})"
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


async def _show_item_view(callback: types.CallbackQuery, ctx_short: str, ctx_id: str | int, item_id: int, db=None, sort_by: str = "d"):
    """Show full single item view with navigation and actions."""
    if db is None:
        db = callback.bot.get("db")
    user_id = callback.from_user.id
    context_type = _CTX_REV.get(ctx_short, "recent")

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await callback.answer("\u0417\u0430\u043f\u0438\u0441\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430.")
        return

    # Get category info for display
    if item.get("category_id"):
        cats = await queries.get_all_categories(db, user_id)
        cat = next((c for c in cats if c["id"] == item["category_id"]), None)
        if cat:
            item["category_name"] = cat["name"]
            item["category_emoji"] = cat.get("emoji", "\U0001f4c1")

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
            text="\u2b05\ufe0f \u041f\u0440\u0435\u0434",
            callback_data=f"vn:{ctx_short}:{ctx_id}:{nav['prev_id']}",
        ))
    if position and total:
        nav_row.append(InlineKeyboardButton(text=f"{position}/{total}", callback_data="noop"))
    if nav and nav.get("next_id"):
        nav_row.append(InlineKeyboardButton(
            text="\u0421\u043b\u0435\u0434 \u27a1\ufe0f",
            callback_data=f"vn:{ctx_short}:{ctx_id}:{nav['next_id']}",
        ))
    if nav_row:
        buttons.append(nav_row)

    # Action row 1: pin, move, delete
    actions1 = []
    if item.get("is_pinned"):
        actions1.append(InlineKeyboardButton(text="\U0001f4cc \u041e\u0442\u043a\u0440\u0435\u043f\u0438\u0442\u044c", callback_data=f"va:pin:{item_id}"))
    else:
        actions1.append(InlineKeyboardButton(text="\U0001f4cc \u0417\u0430\u043a\u0440\u0435\u043f\u0438\u0442\u044c", callback_data=f"va:pin:{item_id}"))
    actions1.append(InlineKeyboardButton(text="\U0001f4c2 \u041f\u0435\u0440\u0435\u043c\u0435\u0441\u0442\u0438\u0442\u044c", callback_data=f"va:move:{item_id}"))
    actions1.append(InlineKeyboardButton(text="\U0001f5d1 \u0423\u0434\u0430\u043b\u0438\u0442\u044c", callback_data=f"va:del:{item_id}"))
    buttons.append(actions1)

    # Forward original post button
    if item.get("forward_url"):
        buttons.append([InlineKeyboardButton(text="\U0001f4e8 \u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b", url=item["forward_url"])])

    # Action row 2: tags, note, related, collection
    actions2 = []
    actions2.append(InlineKeyboardButton(text="\U0001f3f7 \u0422\u0435\u0433\u0438", callback_data=f"va:tags:{item_id}"))
    actions2.append(InlineKeyboardButton(text="\u270f\ufe0f \u0417\u0430\u043c\u0435\u0442\u043a\u0430", callback_data=f"va:note:{item_id}"))
    actions2.append(InlineKeyboardButton(text="\U0001f517 \u041f\u043e\u0445\u043e\u0436\u0438\u0435", callback_data=f"va:rel:{item_id}"))
    actions2.append(InlineKeyboardButton(text="\U0001f4c1+", callback_data=f"va:coll:{item_id}"))
    buttons.append(actions2)

    # Back to list row
    back_offset = max(0, ((position - 1) // PAGE_SIZE) * PAGE_SIZE) if position else 0
    buttons.append([InlineKeyboardButton(
        text="\U0001f519 \u041a \u0441\u043f\u0438\u0441\u043a\u0443",
        callback_data=f"vl:{ctx_short}:{ctx_id}:{back_offset}:{sort_by}",
    )])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


async def _show_collections(callback_or_msg, db=None):
    """Show collections list. Works with both callback and message."""
    if isinstance(callback_or_msg, types.CallbackQuery):
        user_id = callback_or_msg.from_user.id
    else:
        user_id = callback_or_msg.from_user.id

    colls = await queries.get_collections(db, user_id)

    buttons = []
    for coll in colls:
        emoji = coll.get("emoji", "\U0001f4c1")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {coll['name']} ({coll['item_count']})",
            callback_data=f"bc:{coll['id']}:0",
        )])
    buttons.append([InlineKeyboardButton(text="\u2795 \u041d\u043e\u0432\u0430\u044f \u043a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u044f", callback_data="bm:newcoll")])
    buttons.append([InlineKeyboardButton(text="\U0001f519 \u041a \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u044f\u043c", callback_data="bm:cats")])

    text = "\U0001f4c1 <b>\u041a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u0438:</b>" if colls else "\U0001f4c1 <b>\u041a\u043e\u043b\u043b\u0435\u043a\u0446\u0438\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.</b>"
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(callback_or_msg, types.CallbackQuery):
        await callback_or_msg.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback_or_msg.answer()
    else:
        await callback_or_msg.reply(text, reply_markup=markup, parse_mode="HTML")
