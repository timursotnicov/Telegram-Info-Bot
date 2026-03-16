"""Persistent keyboard handlers and state dispatcher.

This router MUST be registered before save.router so it intercepts
keyboard button texts and state-based text input before they get saved as items.
"""

from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import ForceReply

from savebot.db import queries
from savebot.db.state_store import get_state, set_state, delete_state

router = Router()
logger = logging.getLogger(__name__)

BUTTON_TEXTS = {"📂 Browse", "🔍 Search", "📌 Pinned", "🕐 Recent", "📖 Read List", "⚙️ Settings"}


# ── State dispatcher ──────────────────────────────────────
# Handles free-text input when the bot is awaiting user response
# (e.g. search query, category rename, new category name).
# Must be registered BEFORE button handler so states take priority.

@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(BUTTON_TEXTS))
async def state_dispatcher(message: types.Message, db=None):
    user_id = message.from_user.id
    text = message.text.strip()
    logger.info("State dispatcher: checking states for user %d, text=%s", user_id, text[:50])

    # Check search prompt state
    state = await get_state(db, f"search_prompt_{user_id}")
    if state is not None:
        logger.info("State dispatcher: found search_prompt state for user %d", user_id)
        await delete_state(db, f"search_prompt_{user_id}")
        from savebot.handlers.browse import cmd_search
        await cmd_search(message, db=db, query_override=text)
        return

    # Check rename_cat state
    state = await get_state(db, f"rename_cat_{user_id}")
    if state is not None:
        logger.info("State dispatcher: found rename_cat state for user %d", user_id)
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
    if state is not None:
        logger.info("State dispatcher: found awaiting_cat state for user %d", user_id)
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
                forward_url=pending.get("forward_url"),
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
    if state is not None:
        logger.info("State dispatcher: found new_browse_cat state for user %d", user_id)
        await delete_state(db, f"new_browse_cat_{user_id}")
        try:
            cat = await queries.create_category_manual(db, user_id, text)
            await message.reply(f"✅ Категория «{text}» создана!")
        except ValueError as e:
            await message.reply(f"⚠️ {e}")
        return

    # Check edit_tags state
    state = await get_state(db, f"edit_tags_{user_id}")
    if state is not None:
        logger.info("State dispatcher: found edit_tags state for user %d", user_id)
        await delete_state(db, f"edit_tags_{user_id}")
        item_id = state["item_id"]
        # Parse tags: split by space/comma, strip #, lowercase
        new_tags = [t.strip().strip("#").lower().replace("-", "_") for t in text.replace(",", " ").split() if t.strip()]
        if new_tags:
            await queries.update_item_tags(db, user_id, item_id, new_tags)
            tags_str = " ".join(f"#{t}" for t in new_tags)
            await message.reply(f"✅ Теги обновлены: {tags_str}")
        else:
            await message.reply("⚠️ Введите хотя бы один тег.")
        return

    # Check edit_note state
    state = await get_state(db, f"edit_note_{user_id}")
    if state is not None:
        logger.info("State dispatcher: found edit_note state for user %d", user_id)
        await delete_state(db, f"edit_note_{user_id}")
        item_id = state["item_id"]
        await queries.update_item_note(db, user_id, item_id, text)
        await message.reply("✅ Заметка сохранена")
        return

    # No state matched — let save.py catch it as content to save
    logger.info("State dispatcher: no state found for user %d, skipping to save handler", user_id)
    from aiogram.dispatcher.event.bases import SkipHandler
    raise SkipHandler


# ── Keyboard button handlers ──────────────────────────────

@router.message(F.text.in_(BUTTON_TEXTS))
async def handle_keyboard_button(message: types.Message, db=None):
    # Clear any pending states when user presses a keyboard button
    user_id = message.from_user.id
    for prefix in ("search_prompt_", "rename_cat_", "new_browse_cat_", "awaiting_", "edit_tags_", "edit_note_"):
        await delete_state(db, f"{prefix}{user_id}")

    text = message.text

    if text == "📂 Browse":
        from savebot.handlers.browse import cmd_browse
        await cmd_browse(message, db=db)

    elif text == "🔍 Search":
        user_id = message.from_user.id
        await set_state(db, f"search_prompt_{user_id}", user_id, "search_prompt", {})
        await message.reply(
            "🔍 Введите поисковый запрос:",
            reply_markup=ForceReply(input_field_placeholder="Поиск..."),
        )

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
