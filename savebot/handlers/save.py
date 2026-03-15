"""Save flow handler — receives content, classifies with AI, shows inline buttons."""

from __future__ import annotations

import json
import logging

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.services.ai_classifier import classify_content
from savebot.services.link_preview import extract_url, fetch_link_metadata

logger = logging.getLogger(__name__)
router = Router()

# Temporary storage for pending saves: {user_id}_{message_id} -> data
_pending: dict[str, dict] = {}


def _format_suggestion(ai: dict) -> str:
    tags_str = " ".join(f"#{t}" for t in ai["tags"])
    text = (
        f"🔖 <b>AI предлагает:</b>\n"
        f"Категория: {ai['emoji']} {ai['category']}\n"
        f"Теги: {tags_str}\n"
    )
    if ai.get("summary"):
        text += f"<i>Саммари: {ai['summary']}</i>\n"
    return text


def _save_keyboard(pending_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Сохранить", callback_data=f"save_confirm:{pending_key}"),
            InlineKeyboardButton(text="🔖 Другая категория", callback_data=f"save_change_cat:{pending_key}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"save_cancel:{pending_key}"),
        ]
    ])


async def _process_content(message: types.Message, db):
    """Common logic for processing any incoming content."""
    content_type = "text"
    content_text = ""
    url = None
    file_id = None
    source = None

    # Forwarded message
    if message.forward_origin:
        content_type = "forward"
        content_text = message.text or message.caption or ""
        if hasattr(message.forward_origin, "sender_user") and message.forward_origin.sender_user:
            source = message.forward_origin.sender_user.full_name
        elif hasattr(message.forward_origin, "chat") and message.forward_origin.chat:
            source = message.forward_origin.chat.title or message.forward_origin.chat.full_name
        elif hasattr(message.forward_origin, "sender_user_name"):
            source = message.forward_origin.sender_user_name

    # File / photo / document
    elif message.document:
        content_type = "file"
        content_text = message.caption or message.document.file_name or "document"
        file_id = message.document.file_id
    elif message.photo:
        content_type = "file"
        content_text = message.caption or "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        content_type = "file"
        content_text = message.caption or "video"
        file_id = message.video.file_id
    elif message.audio:
        content_type = "file"
        content_text = message.caption or message.audio.title or "audio"
        file_id = message.audio.file_id
    elif message.voice:
        content_type = "file"
        content_text = message.caption or "voice message"
        file_id = message.voice.file_id

    # Text with URL
    elif message.text:
        detected_url = extract_url(message.text)
        if detected_url:
            content_type = "link"
            url = detected_url
            meta = await fetch_link_metadata(url)
            title = meta.get("title", "")
            desc = meta.get("description", "")
            content_text = message.text
            if title:
                content_text += f"\n\nTitle: {title}"
            if desc:
                content_text += f"\nDescription: {desc}"
        else:
            content_type = "text"
            content_text = message.text

    if not content_text:
        content_text = message.text or message.caption or ""

    # Check for duplicates
    dup = await queries.find_duplicate(db, content_text, url)
    if dup:
        await message.reply(
            f"⚠️ Похоже, это уже сохранено (ID: {dup['id']}).\n"
            f"Отправьте /edit {dup['id']} чтобы изменить.",
            parse_mode="HTML",
        )
        return

    # Get existing categories and tags for AI
    categories = await queries.get_all_categories(db)
    tags = await queries.get_all_tags(db)
    tag_names = [t["tag"] for t in tags]

    # Classify with AI
    ai_result = await classify_content(content_text, categories, tag_names)

    if not ai_result:
        ai_result = {
            "category": "Inbox",
            "emoji": "📥",
            "tags": [],
            "summary": "",
        }

    # Store pending save
    pending_key = f"{message.from_user.id}_{message.message_id}"
    _pending[pending_key] = {
        "content_type": content_type,
        "content_text": content_text,
        "url": url,
        "file_id": file_id,
        "source": source,
        "ai_result": ai_result,
        "tg_message_id": message.message_id,
    }

    text = _format_suggestion(ai_result)
    await message.reply(text, reply_markup=_save_keyboard(pending_key), parse_mode="HTML")


# ── Message handlers ────────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message, db=None):
    await _process_content(message, db)


@router.message(F.photo)
async def handle_photo(message: types.Message, db=None):
    await _process_content(message, db)


@router.message(F.document)
async def handle_document(message: types.Message, db=None):
    await _process_content(message, db)


@router.message(F.video)
async def handle_video(message: types.Message, db=None):
    await _process_content(message, db)


@router.message(F.audio)
async def handle_audio(message: types.Message, db=None):
    await _process_content(message, db)


@router.message(F.voice)
async def handle_voice(message: types.Message, db=None):
    await _process_content(message, db)


@router.message(F.forward_origin)
async def handle_forward(message: types.Message, db=None):
    await _process_content(message, db)


# ── Callback handlers ──────────────────────────────────────

@router.callback_query(F.data.startswith("save_confirm:"))
async def on_save_confirm(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    data = _pending.pop(pending_key, None)
    if not data:
        await callback.answer("Сессия истекла. Отправьте контент заново.")
        return

    ai = data["ai_result"]
    cat = await queries.get_or_create_category(db, ai["category"], ai.get("emoji", "📁"))

    item_id = await queries.save_item(
        db,
        category_id=cat["id"],
        content_type=data["content_type"],
        content_text=data["content_text"],
        tags=ai["tags"],
        url=data.get("url"),
        file_id=data.get("file_id"),
        source=data.get("source"),
        ai_summary=ai.get("summary"),
        tg_message_id=data.get("tg_message_id"),
    )

    tags_str = " ".join(f"#{t}" for t in ai["tags"])
    await callback.message.edit_text(
        f"✅ Сохранено в {cat.get('emoji', '📁')} {cat['name']} / {tags_str}\n"
        f"ID: {item_id}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("save_change_cat:"))
async def on_change_category(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    data = _pending.get(pending_key)
    if not data:
        await callback.answer("Сессия истекла.")
        return

    categories = await queries.get_all_categories(db)
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(
            text=f"{cat.get('emoji', '📁')} {cat['name']}",
            callback_data=f"save_pick_cat:{pending_key}:{cat['id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text="➕ Создать новую",
        callback_data=f"save_new_cat:{pending_key}",
    )])

    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("save_pick_cat:"))
async def on_pick_category(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    pending_key = parts[1]
    cat_id = int(parts[2])

    data = _pending.pop(pending_key, None)
    if not data:
        await callback.answer("Сессия истекла.")
        return

    ai = data["ai_result"]
    item_id = await queries.save_item(
        db,
        category_id=cat_id,
        content_type=data["content_type"],
        content_text=data["content_text"],
        tags=ai["tags"],
        url=data.get("url"),
        file_id=data.get("file_id"),
        source=data.get("source"),
        ai_summary=ai.get("summary"),
        tg_message_id=data.get("tg_message_id"),
    )

    # Fetch category info for display
    cats = await queries.get_all_categories(db)
    cat = next((c for c in cats if c["id"] == cat_id), {"name": "Unknown", "emoji": "📁"})
    tags_str = " ".join(f"#{t}" for t in ai["tags"])

    await callback.message.edit_text(
        f"✅ Сохранено в {cat.get('emoji', '📁')} {cat['name']} / {tags_str}\n"
        f"ID: {item_id}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("save_new_cat:"))
async def on_new_category(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    if pending_key not in _pending:
        await callback.answer("Сессия истекла.")
        return

    await callback.message.edit_text(
        "Введите название новой категории (или отправьте /cancel):",
        parse_mode="HTML",
    )
    # Store that we're waiting for new category name
    _pending[pending_key]["awaiting_new_cat"] = True
    _pending[f"awaiting_{callback.from_user.id}"] = pending_key
    await callback.answer()


@router.callback_query(F.data.startswith("save_cancel:"))
async def on_save_cancel(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    _pending.pop(pending_key, None)
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()
