"""Persistent keyboard handlers and state dispatcher.

This router MUST be registered before save.router so it intercepts
keyboard button texts and state-based text input before they get saved as items.
"""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command

from savebot.db import queries
from savebot.db.state_store import get_state, set_state, delete_state

router = Router()

BUTTON_TEXTS = {"📂 Browse", "🔍 Search", "📌 Pinned", "🕐 Recent", "📖 Read List", "⚙️ Settings"}


# ── State dispatcher ──────────────────────────────────────
# Handles free-text input when the bot is awaiting user response
# (e.g. search query, category rename, new category name).
# Must be registered BEFORE button handler so states take priority.

@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(BUTTON_TEXTS))
async def state_dispatcher(message: types.Message, db=None):
    user_id = message.from_user.id
    text = message.text.strip()

    # Check search prompt state
    state = await get_state(db, f"search_prompt_{user_id}")
    if state:
        await delete_state(db, f"search_prompt_{user_id}")
        from savebot.handlers.browse import cmd_search
        # Fake the message text to look like /search <query>
        message.text = f"/search {text}"
        await cmd_search(message, db=db)
        return

    # Check rename_cat state
    state = await get_state(db, f"rename_cat_{user_id}")
    if state:
        await delete_state(db, f"rename_cat_{user_id}")
        cat_id = state["cat_id"]
        renamed = await queries.rename_category(db, user_id, cat_id, text)
        if renamed:
            await message.reply(f"✅ Категория переименована в «{text}»")
        else:
            await message.reply("⚠️ Категория не найдена.")
        return

    # Check awaiting_cat state (manual save flow — user typing new category name)
    state = await get_state(db, f"awaiting_{user_id}")
    if state:
        pending_key = state["pending_key"]
        pending = await get_state(db, pending_key)
        if pending:
            cat = await queries.get_or_create_category(db, user_id, text)
            ai = pending.get("ai_result", {})
            item_id = await queries.save_item(
                db, user_id,
                category_id=cat["id"],
                content_type=pending.get("content_type", "text"),
                content_text=pending.get("content_text", ""),
                tags=ai.get("tags", []),
                url=pending.get("url"), file_id=pending.get("file_id"),
                source=pending.get("source"), ai_summary=ai.get("summary"),
                tg_message_id=pending.get("tg_message_id"),
            )
            tags_str = " ".join(f"#{t}" for t in ai.get("tags", []))
            await message.reply(
                f"✅ Сохранено в {cat.get('emoji', '📁')} {cat['name']} / {tags_str}\nID: {item_id}",
            )
            await delete_state(db, pending_key)
        await delete_state(db, f"awaiting_{user_id}")
        return

    # Check new_browse_cat state (creating category from browse hub)
    state = await get_state(db, f"new_browse_cat_{user_id}")
    if state:
        await delete_state(db, f"new_browse_cat_{user_id}")
        try:
            cat = await queries.create_category_manual(db, user_id, text)
            await message.reply(f"✅ Категория «{text}» создана!")
        except ValueError as e:
            await message.reply(f"⚠️ {e}")
        return

    # No state matched — let save.py catch it as content to save
    from aiogram.dispatcher.event.bases import SkipHandler
    raise SkipHandler


# ── Keyboard button handlers ──────────────────────────────

@router.message(F.text.in_(BUTTON_TEXTS))
async def handle_keyboard_button(message: types.Message, db=None):
    text = message.text

    if text == "📂 Browse":
        from savebot.handlers.browse import cmd_browse
        await cmd_browse(message, db=db)

    elif text == "🔍 Search":
        user_id = message.from_user.id
        await set_state(db, f"search_prompt_{user_id}", user_id, "search_prompt", {})
        await message.reply("🔍 Введите поисковый запрос:")

    elif text == "📌 Pinned":
        from savebot.handlers.browse import cmd_pinned
        await cmd_pinned(message, db=db)

    elif text == "🕐 Recent":
        from savebot.handlers.browse import cmd_recent
        await cmd_recent(message, db=db)

    elif text == "📖 Read List":
        from savebot.handlers.browse import cmd_readlist
        await cmd_readlist(message, db=db)

    elif text == "⚙️ Settings":
        from savebot.handlers.settings import cmd_settings
        await cmd_settings(message, db=db)
