"""Save flow handler — auto-save with AI categorization."""
from __future__ import annotations
import html
import logging

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.db.state_store import get_state, set_state, delete_state
from savebot.services.ai_classifier import classify_content
from savebot.services.connections import find_related_items
from savebot.services.link_preview import extract_url, fetch_link_metadata
from savebot.services.ocr import extract_text_from_image

logger = logging.getLogger(__name__)
router = Router()


def _category_buttons(
    categories: list[dict],
    item_id: int,
    highlight_id: int | None = None,
    callback_prefix: str = "autosave_pick",
) -> list[list[InlineKeyboardButton]]:
    """Build category selection buttons in a grid (3 per row)."""
    buttons = []
    row = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        mark = "✅ " if cat["id"] == highlight_id else ""
        row.append(InlineKeyboardButton(
            text=f"{mark}{emoji} {cat['name']}",
            callback_data=f"{callback_prefix}:{item_id}:{cat['id']}",
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


def _post_save_keyboard(categories: list[dict], item_id: int, saved_cat_id: int) -> InlineKeyboardMarkup:
    buttons = _category_buttons(categories, item_id, highlight_id=saved_cat_id)
    buttons.append([
        InlineKeyboardButton(text="📌 Pin", callback_data=f"autosave_pin:{item_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"autosave_delete:{item_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _confirm_keyboard(pending_key: str) -> InlineKeyboardMarkup:
    """For manual save mode (auto_save=False)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Сохранить", callback_data=f"save_confirm:{pending_key}"),
        InlineKeyboardButton(text="🔖 Другая категория", callback_data=f"save_change_cat:{pending_key}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"save_cancel:{pending_key}"),
    ]])


async def _detect_content(message: types.Message):
    """Detect content type and extract text/metadata."""
    content_type = "text"
    content_text = ""
    url = None
    file_id = None
    source = None
    forward_url = None

    if message.forward_origin:
        content_type = "forward"
        content_text = message.text or message.caption or ""
        if hasattr(message.forward_origin, "sender_user") and message.forward_origin.sender_user:
            source = message.forward_origin.sender_user.full_name
        elif hasattr(message.forward_origin, "chat") and message.forward_origin.chat:
            source = message.forward_origin.chat.title or message.forward_origin.chat.full_name
            # Build forward_url for MessageOriginChannel
            chat = message.forward_origin.chat
            if chat.username:
                forward_url = f"https://t.me/{chat.username}/{message.forward_origin.message_id}"
            else:
                clean_id = str(chat.id).replace("-100", "")
                forward_url = f"https://t.me/c/{clean_id}/{message.forward_origin.message_id}"
        elif hasattr(message.forward_origin, "sender_user_name"):
            source = message.forward_origin.sender_user_name
        # Extract URL from entities for forwards
        entities = message.entities or message.caption_entities or []
        for entity in entities:
            if entity.type == "url":
                text = message.text or message.caption or ""
                url = text[entity.offset:entity.offset + entity.length]
                break
            elif entity.type == "text_link":
                url = entity.url
                break
    elif message.document:
        content_type = "file"
        content_text = message.caption or message.document.file_name or "document"
        file_id = message.document.file_id
    elif message.photo:
        content_type = "file"
        file_id = message.photo[-1].file_id
        # OCR: extract text from image via Gemini Flash vision
        ocr_text = await extract_text_from_image(message.bot, file_id)
        if ocr_text:
            content_text = ocr_text
            if message.caption:
                content_text = f"{message.caption}\n\n[OCR]: {ocr_text}"
        else:
            content_text = message.caption or "photo"
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

    return content_type, content_text, url, file_id, source, forward_url


async def _quick_capture(message: types.Message, db) -> bool:
    """Handle '!' prefix — save to Inbox without AI. Returns True if handled."""
    if not message.text or not message.text.startswith("!"):
        return False

    text = message.text[1:].strip()
    if not text:
        return False

    user_id = message.from_user.id
    raznoye = await queries.get_category_by_name(db, user_id, "Разное")
    if not raznoye:
        raznoye = await queries.get_or_create_category(db, user_id, "Разное", "📥")
    await queries.save_item(
        db, user_id,
        category_id=raznoye["id"],
        content_type="text",
        content_text=text,
        tags=[],
        ai_summary=text[:100],
    )
    await message.reply("✅ Сохранено в 📥 Разное")
    return True


async def _classify_with_ai(db, user_id: int, content_text: str) -> dict:
    """Classify content with AI, fallback to Разное."""
    categories = await queries.get_all_categories(db, user_id)
    tags = await queries.get_all_tags(db, user_id)
    tag_names = [t["tag"] for t in tags]
    ai_result = await classify_content(content_text, categories, tag_names)
    if not ai_result:
        ai_result = {"category": "Разное", "emoji": "📥", "tags": [], "summary": ""}
    return ai_result


async def _auto_save_flow(message, db, user_id, ai_result,
                          content_type, content_text, url, file_id, source, forward_url):
    """AUTO-SAVE: save immediately and show post-save keyboard."""
    cat = await queries.get_category_by_name(db, user_id, ai_result["category"])
    if not cat:
        cat = await queries.get_category_by_name(db, user_id, "Разное")
    if not cat:
        cat = await queries.get_or_create_category(db, user_id, "Разное", "📥")
    item_id = await queries.save_item(
        db, user_id,
        category_id=cat["id"],
        content_type=content_type,
        content_text=content_text,
        tags=ai_result["tags"],
        url=url, file_id=file_id, source=source,
        ai_summary=ai_result.get("summary"),
        tg_message_id=message.message_id,
        forward_url=forward_url,
    )

    tags_str = " ".join(f"#{t}" for t in ai_result["tags"])
    text = f"✅ Сохранено в {cat.get('emoji', '📁')} <b>{cat['name']}</b>"
    if tags_str:
        text += f" / {tags_str}"
    if ai_result.get("summary"):
        text += f"\n<i>{html.escape(ai_result['summary'])}</i>"

    # Find related items
    try:
        related = await find_related_items(
            db, item_id, user_id,
            category_id=cat["id"],
            tags=ai_result["tags"],
            source=source,
        )
        if related:
            text += "\n\n🔗 <b>Похожие записи:</b>"
            for r in related:
                r_summary = r.get("ai_summary") or r["content_text"][:60]
                text += f"\n  #{r['id']} {html.escape(r_summary)}"
    except Exception:
        logger.exception("find_related_items failed for item %d", item_id)

    categories = await queries.get_all_categories(db, user_id)
    await message.reply(text, reply_markup=_post_save_keyboard(categories, item_id, cat["id"]), parse_mode="HTML")


async def _manual_save_flow(message, db, user_id, ai_result,
                            content_type, content_text, url, file_id, source, forward_url):
    """MANUAL SAVE: show confirmation (old flow)."""
    pending_key = f"{user_id}_{message.message_id}"
    await set_state(db, pending_key, user_id, "save", {
        "content_type": content_type,
        "content_text": content_text,
        "url": url,
        "file_id": file_id,
        "source": source,
        "ai_result": ai_result,
        "tg_message_id": message.message_id,
        "forward_url": forward_url,
    })

    tags_str = " ".join(f"#{t}" for t in ai_result["tags"])
    text = (
        f"🔖 <b>AI предлагает:</b>\n"
        f"Категория: {ai_result['emoji']} {ai_result['category']}\n"
        f"Теги: {tags_str}\n"
    )
    if ai_result.get("summary"):
        text += f"<i>Саммари: {html.escape(ai_result['summary'])}</i>\n"

    await message.reply(text, reply_markup=_confirm_keyboard(pending_key), parse_mode="HTML")


async def _process_content(message: types.Message, db):
    """Process incoming content — auto-save or manual mode."""
    user_id = message.from_user.id
    await queries.ensure_default_categories(db, user_id)

    # Quick capture: '!' prefix saves to Разное without AI
    if await _quick_capture(message, db):
        return

    content_type, content_text, url, file_id, source, forward_url = await _detect_content(message)

    # Check for duplicates
    dup = await queries.find_duplicate(
        db, user_id, content_text, url,
        forward_url=forward_url,
        tg_message_id=message.message_id,
    )
    if dup:
        await message.reply(
            f"⚠️ Похоже, это уже сохранено (ID: {dup['id']}).\n"
            f"Отправьте /edit {dup['id']} чтобы изменить.",
            parse_mode="HTML",
        )
        return

    # Classify with AI
    ai_result = await _classify_with_ai(db, user_id, content_text)

    # Check user preferences
    prefs = await queries.get_user_preferences(db, user_id)

    if prefs.get("auto_save", 1):
        await _auto_save_flow(message, db, user_id, ai_result,
                              content_type, content_text, url, file_id, source, forward_url)
    else:
        await _manual_save_flow(message, db, user_id, ai_result,
                                content_type, content_text, url, file_id, source, forward_url)


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


# ── Auto-save callbacks (work with item_id) ───────────────

@router.callback_query(F.data.startswith("autosave_change:"))
async def on_autosave_change(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    categories = await queries.get_all_categories(db, user_id)

    buttons = _category_buttons(categories, item_id)

    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("autosave_pick:"))
async def on_autosave_pick(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    item_id = int(parts[1])
    cat_id = int(parts[2])
    user_id = callback.from_user.id

    await queries.update_item_category(db, user_id, item_id, cat_id)
    cats = await queries.get_all_categories(db, user_id)
    cat = next((c for c in cats if c["id"] == cat_id), {"name": "Unknown", "emoji": "📁"})

    await callback.message.edit_text(
        f"✅ Сохранено в {cat.get('emoji', '📁')} <b>{cat['name']}</b>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("autosave_pin:"))
async def on_autosave_pin(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await queries.pin_item(db, user_id, item_id)
    await callback.answer("📌 Закреплено!")


@router.callback_query(F.data.startswith("autosave_delete:"))
async def on_autosave_delete(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await queries.delete_item(db, user_id, item_id)
    await callback.message.edit_text("🗑 Запись удалена.")
    await callback.answer()


# ── Manual save callbacks (work with pending_key via state_store) ──

@router.callback_query(F.data.startswith("save_confirm:"))
async def on_save_confirm(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    data = await get_state(db, pending_key)
    if not data:
        await callback.answer("Сессия истекла. Отправьте контент заново.")
        return
    await delete_state(db, pending_key)

    user_id = callback.from_user.id
    ai = data["ai_result"]
    cat = await queries.get_category_by_name(db, user_id, ai["category"])
    if not cat:
        cat = await queries.get_category_by_name(db, user_id, "Разное")
    if not cat:
        cat = await queries.get_or_create_category(db, user_id, "Разное", "📥")

    item_id = await queries.save_item(
        db, user_id,
        category_id=cat["id"],
        content_type=data["content_type"],
        content_text=data["content_text"],
        tags=ai["tags"],
        url=data.get("url"), file_id=data.get("file_id"),
        source=data.get("source"), ai_summary=ai.get("summary"),
        tg_message_id=data.get("tg_message_id"),
        forward_url=data.get("forward_url"),
    )

    tags_str = " ".join(f"#{t}" for t in ai["tags"])
    await callback.message.edit_text(
        f"✅ Сохранено в {cat.get('emoji', '📁')} {cat['name']} / {tags_str}\nID: {item_id}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("save_change_cat:"))
async def on_change_category(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    data = await get_state(db, pending_key)
    if not data:
        await callback.answer("Сессия истекла.")
        return

    user_id = callback.from_user.id
    categories = await queries.get_all_categories(db, user_id)
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
    buttons.append([InlineKeyboardButton(text="➕ Создать новую", callback_data=f"save_new_cat:{pending_key}")])

    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("save_pick_cat:"))
async def on_pick_category(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    pending_key = parts[1]
    cat_id = int(parts[2])

    data = await get_state(db, pending_key)
    if not data:
        await callback.answer("Сессия истекла.")
        return
    await delete_state(db, pending_key)

    user_id = callback.from_user.id
    ai = data["ai_result"]
    item_id = await queries.save_item(
        db, user_id,
        category_id=cat_id,
        content_type=data["content_type"],
        content_text=data["content_text"],
        tags=ai["tags"],
        url=data.get("url"), file_id=data.get("file_id"),
        source=data.get("source"), ai_summary=ai.get("summary"),
        tg_message_id=data.get("tg_message_id"),
        forward_url=data.get("forward_url"),
    )

    cats = await queries.get_all_categories(db, user_id)
    cat = next((c for c in cats if c["id"] == cat_id), {"name": "Unknown", "emoji": "📁"})
    tags_str = " ".join(f"#{t}" for t in ai["tags"])

    await callback.message.edit_text(
        f"✅ Сохранено в {cat.get('emoji', '📁')} {cat['name']} / {tags_str}\nID: {item_id}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("save_new_cat:"))
async def on_new_category(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    data = await get_state(db, pending_key)
    if not data:
        await callback.answer("Сессия истекла.")
        return

    await callback.message.edit_text("Введите название новой категории (или отправьте /cancel):", parse_mode="HTML")
    # Mark that we're waiting for new category name
    data["awaiting_new_cat"] = True
    await set_state(db, pending_key, callback.from_user.id, "save", data)
    await set_state(db, f"awaiting_{callback.from_user.id}", callback.from_user.id, "awaiting_cat", {"pending_key": pending_key})
    await callback.answer()


@router.callback_query(F.data.startswith("save_cancel:"))
async def on_save_cancel(callback: types.CallbackQuery, db=None):
    pending_key = callback.data.split(":", 1)[1]
    await delete_state(db, pending_key)
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()
