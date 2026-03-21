"""Management handlers: /edit, /delete, /stats, /categories, /export, /start, /help, /clear."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from savebot.db import queries
from savebot.db.state_store import set_state

router = Router()
logger = logging.getLogger(__name__)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📂 Все записи"), KeyboardButton(text="🔍 Поиск")],
        [KeyboardButton(text="🕐 Недавние"), KeyboardButton(text="⚙️ Настройки")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# Track bot message IDs per user for /clear (in-memory, max 100 per user)
_bot_messages: dict[int, list[int]] = defaultdict(list)
_MAX_TRACKED = 100


def track_message(user_id: int, message_id: int):
    """Track a bot message ID for later cleanup via /clear."""
    msgs = _bot_messages[user_id]
    msgs.append(message_id)
    if len(msgs) > _MAX_TRACKED:
        _bot_messages[user_id] = msgs[-_MAX_TRACKED:]


# ── /start and /help ────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: types.Message, **kwargs):
    result = await message.reply(
        "👋 <b>Привет! Я SaveBot</b> — твоя вторая память.\n\n"
        "Просто отправь мне текст, ссылку, фото или файл — "
        "я сохраню и организую автоматически.\n\n"
        "Используй кнопки внизу для быстрого доступа:\n"
        "📂 Все записи — просмотр по категориям\n"
        "🔍 Поиск — найти нужное\n"
        "🕐 Недавние — последние записи\n"
        "⚙️ Настройки — настройки бота\n"
        "ℹ️ Подробнее: /help",
        reply_markup=MAIN_KEYBOARD,
        parse_mode="HTML",
    )
    track_message(message.from_user.id, result.message_id)


@router.message(Command("help"))
async def cmd_help(message: types.Message, **kwargs):
    result = await message.reply(
        "📖 <b>Справка SaveBot</b>\n\n"
        "Основные команды:\n"
        "/browse — просмотр по категориям\n"
        "/search &lt;запрос&gt; — поиск по записям\n"
        "/recent — последние записи\n"
        "/settings — настройки бота\n"
        "/help — эта справка\n\n"
        "Остальные действия доступны через кнопки "
        "в нижней панели клавиатуры.",
        parse_mode="HTML",
    )
    track_message(message.from_user.id, result.message_id)


# ── /clear ─────────────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: types.Message, **kwargs):
    user_id = message.from_user.id
    msg_ids = _bot_messages.pop(user_id, [])
    deleted = 0
    for msg_id in msg_ids:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            deleted += 1
        except TelegramBadRequest:
            pass  # Message too old (>48h) or already deleted
    # Also try to delete the /clear command message itself
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    if deleted == 0 and not msg_ids:
        result = await message.answer("🧹 Нет сообщений для очистки.")
        track_message(user_id, result.message_id)


# ── /stats ──────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    stats = await queries.get_stats(db, user_id)
    await message.reply(
        f"📊 <b>Статистика:</b>\n\n"
        f"📝 Записей: {stats['items']}\n"
        f"📂 Категорий: {stats['categories']}\n"
        f"🏷 Тегов: {stats['tags']}",
        parse_mode="HTML",
    )


# ── /categories ─────────────────────────────────────────────

@router.message(Command("categories"))
async def cmd_categories(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await message.reply("Категорий пока нет.")
        return

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {cat['name']} ({cat['item_count']})",
                callback_data=f"cat_info:{cat['id']}",
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"cat_rename:{cat['id']}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"cat_delete:{cat['id']}",
            ),
        ])

    await message.reply(
        "📂 <b>Управление категориями:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cat_delete:"))
async def on_cat_delete(callback: types.CallbackQuery, db=None):
    cat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    affected = await queries.delete_category(db, user_id, cat_id)
    await callback.message.edit_text(
        f"🗑 Категория удалена. {affected} записей перемещены в «без категории».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_rename:"))
async def on_cat_rename(callback: types.CallbackQuery, db=None):
    await callback.message.edit_text(
        "Введите новое название категории:",
        parse_mode="HTML",
    )
    await set_state(db, f"rename_cat_{callback.from_user.id}", callback.from_user.id, "rename_cat", {"cat_id": int(callback.data.split(":")[1])})
    await callback.answer()


@router.callback_query(F.data.startswith("cat_info:"))
async def on_cat_info(callback: types.CallbackQuery, db=None):
    cat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Get category with tag map for top tags
    tag_map = await queries.get_category_tag_map(db, user_id)
    cat = next((c for c in tag_map if c["id"] == cat_id), None)
    if not cat:
        await callback.message.edit_text("Категория не найдена.")
        await callback.answer()
        return

    emoji = cat.get("emoji", "📁")
    top_tags = cat.get("top_tags", [])[:3]
    tags_str = ", ".join(f"#{t}" for t in top_tags) if top_tags else "нет тегов"

    text = (
        f"{emoji} <b>{cat['name']}</b>\n\n"
        f"📝 Записей: {cat['item_count']}\n"
        f"🏷 Топ теги: {tags_str}"
    )

    buttons = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"cat_rename:{cat_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"cat_delete:{cat_id}"),
    ], [
        InlineKeyboardButton(text="🔙 К категориям", callback_data="cat_back"),
    ]])

    await callback.message.edit_text(text, reply_markup=buttons, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cat_back")
async def on_cat_back(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await callback.message.edit_text("Категорий пока нет.")
        await callback.answer()
        return

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {cat['name']} ({cat['item_count']})",
                callback_data=f"cat_info:{cat['id']}",
            ),
            InlineKeyboardButton(text="✏️", callback_data=f"cat_rename:{cat['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cat_delete:{cat['id']}"),
        ])

    await callback.message.edit_text(
        "📂 <b>Управление категориями:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ── /edit ───────────────────────────────────────────────────

@router.message(Command("edit"))
async def cmd_edit(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /edit &lt;id&gt;")
        return

    try:
        item_id = int(parts[1])
    except ValueError:
        await message.reply("ID должен быть числом.")
        return

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await message.reply(f"Запись #{item_id} не найдена.")
        return

    tags_str = " ".join(f"#{t}" for t in item.get("tags", []))
    text = (
        f"📝 <b>Запись #{item_id}</b>\n"
        f"Тип: {item['content_type']}\n"
        f"Теги: {tags_str}\n"
        f"Текст: {item['content_text'][:200]}\n"
    )

    categories = await queries.get_all_categories(db, user_id)
    buttons = []
    row = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        row.append(InlineKeyboardButton(
            text=f"{emoji} {cat['name']}",
            callback_data=f"edit_cat:{item_id}:{cat['id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await message.reply(
        text + "\nВыберите новую категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("edit_cat:"))
async def on_edit_category(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    item_id = int(parts[1])
    cat_id = int(parts[2])
    user_id = callback.from_user.id

    await queries.update_item_category(db, user_id, item_id, cat_id)
    await callback.message.edit_text(
        f"✅ Категория записи #{item_id} обновлена.",
        parse_mode="HTML",
    )
    await callback.answer()


# ── /delete ─────────────────────────────────────────────────

@router.message(Command("delete"))
async def cmd_delete(message: types.Message, db=None, **kwargs):
    parts = message.text.split()
    if len(parts) >= 2:
        # /delete <id> — direct delete with confirmation
        try:
            item_id = int(parts[1])
        except ValueError:
            await message.reply("ID должен быть числом.")
            return

        buttons = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"dconf:{item_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="dcancel"),
        ]])
        await message.reply(
            f"Удалить запись #{item_id}?",
            reply_markup=buttons,
            parse_mode="HTML",
        )
        return

    # /delete without args — show recent items as delete picker
    user_id = message.from_user.id
    items = await queries.get_recent_items(db, user_id, limit=10)
    if not items:
        await message.reply("Нет записей для удаления.")
        return

    buttons = []
    for item in items:
        title = (item.get("content_text") or "без текста")[:40]
        buttons.append([InlineKeyboardButton(
            text=f"🗑 #{item['id']} {title}",
            callback_data=f"dpick:{item['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="dcancel")])

    await message.reply(
        "🗑 <b>Выберите запись для удаления:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


async def _do_delete_confirm(callback: types.CallbackQuery, db, item_id: int):
    """Shared delete confirmation logic for picker and item view flows."""
    user_id = callback.from_user.id
    deleted = await queries.delete_item(db, user_id, item_id)
    if deleted:
        await callback.message.edit_text(f"🗑 Запись #{item_id} удалена.")
    else:
        await callback.message.edit_text(f"Запись #{item_id} не найдена.")
    await callback.answer()


@router.callback_query(F.data.startswith("dpick:"))
async def on_delete_pick(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[1])
    buttons = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"dconf:{item_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="dcancel"),
    ]])
    await callback.message.edit_text(
        f"Удалить запись #{item_id}?",
        reply_markup=buttons,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dconf:"))
async def on_delete_confirm(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[1])
    await _do_delete_confirm(callback, db, item_id)


@router.callback_query(F.data == "dcancel")
async def on_delete_cancel(callback: types.CallbackQuery, **kwargs):
    await callback.message.edit_text("Отменено.")
    await callback.answer()


# ── /export ─────────────────────────────────────────────────

@router.message(Command("export"))
async def cmd_export(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    items = await queries.export_all(db, user_id)
    if not items:
        await message.reply("Нет данных для экспорта.")
        return

    export_data = json.dumps(items, ensure_ascii=False, indent=2, default=str)

    if len(export_data) > 4000:
        from io import BytesIO
        file = BytesIO(export_data.encode())
        file.name = "savebot_export.json"
        await message.reply_document(
            types.BufferedInputFile(file.getvalue(), filename="savebot_export.json"),
            caption=f"📦 Экспорт: {len(items)} записей",
        )
    else:
        await message.reply(
            f"📦 <b>Экспорт ({len(items)} записей):</b>\n\n"
            f"<pre>{export_data[:3900]}</pre>",
            parse_mode="HTML",
        )
